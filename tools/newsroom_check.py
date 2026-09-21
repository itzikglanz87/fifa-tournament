# -*- coding: utf-8 -*-
"""Is there newsroom news worth a push? Asked of Firestore, answered in JSON.

    python tools/newsroom_check.py            -> decide, print JSON, change nothing
    python tools/newsroom_check.py --commit   -> record the current bulletin as delivered

The phone app writes the finished bulletin to meta/newsroom — only the page
can compute it. This script signs in the same way the app does (anonymously,
through the public web API key), reads that one document, and compares it
with a marker of what was last delivered.

The marker lives in a local file, not in Firestore: the security rules allow
writes to meta/config and meta/newsroom only, and a push checker has no
business widening them.

Output, always one JSON object on stdout:
    {"news": false, "why": "..."}
    {"news": true, "message": "<one-line push>", "text": "<full bulletin>", ...}
Anything unreachable is reported as {"news": false, "why": "..."} so an
unattended run stays silent instead of alarming anyone.
"""
import io, json, os, sys, urllib.request, urllib.error
from datetime import datetime, timezone

API_KEY = "AIzaSyC6jrNqzjqPZLmva-OvrYBQltrThEoR1d4"
PROJECT = "analytics-2bf94"
STATE = os.path.join(os.path.expanduser("~"), ".claude", "scheduled-tasks",
                     "fifa-newsroom-push", "state.json")


def post(url, body):
    req = urllib.request.Request(url, data=json.dumps(body).encode(),
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=20) as r:
        return json.load(r)


def get(url, token):
    req = urllib.request.Request(url, headers={"Authorization": "Bearer " + token})
    with urllib.request.urlopen(req, timeout=20) as r:
        return json.load(r)


def plain(v):
    """Firestore REST values -> plain Python."""
    if "stringValue" in v:  return v["stringValue"]
    if "integerValue" in v: return int(v["integerValue"])
    if "doubleValue" in v:  return v["doubleValue"]
    if "booleanValue" in v: return v["booleanValue"]
    if "nullValue" in v:    return None
    if "mapValue" in v:     return {k: plain(x) for k, x in v["mapValue"].get("fields", {}).items()}
    if "arrayValue" in v:   return [plain(x) for x in v["arrayValue"].get("values", [])]
    return None


def read_bulletin():
    auth = post("https://identitytoolkit.googleapis.com/v1/accounts:signUp?key=" + API_KEY,
                {"returnSecureToken": True})
    doc = get("https://firestore.googleapis.com/v1/projects/%s/databases/(default)/documents/meta/newsroom"
              % PROJECT, auth["idToken"])
    return {k: plain(v) for k, v in doc.get("fields", {}).items()}


def load_state():
    try:
        return json.load(io.open(STATE, encoding="utf-8"))
    except (OSError, ValueError):
        return None


def decide(n, s):
    if s is None:
        return True, "nothing has been delivered yet"
    if n.get("i") != s.get("i"):
        if isinstance(n.get("i"), int) and isinstance(s.get("i"), int) and n["i"] < s["i"]:
            return False, "bulletin is about an older tournament than the last one delivered"
        return True, "a different tournament"
    if (n.get("played") or 0) > (s.get("played") or 0):
        return True, "more results entered"
    if n.get("done") and not s.get("done"):
        return True, "the tournament has ended"
    return False, "nothing new since the last push"


def message(n):
    head = (n.get("headline") or "").strip()
    if n.get("done"):
        msg = "טורניר %s הסתיים · %s" % (n.get("num"), head)
    else:
        msg = "טורניר %s · %s מתוך %s · %s" % (n.get("num"), n.get("played"), n.get("total"), head)
    return msg[:195]


def main():
    commit = "--commit" in sys.argv
    try:
        n = read_bulletin()
    except (urllib.error.URLError, OSError, KeyError, ValueError) as e:
        print(json.dumps({"news": False, "why": "firestore unreachable: %s" % e}, ensure_ascii=False))
        return
    if not n:
        print(json.dumps({"news": False, "why": "no bulletin yet"}, ensure_ascii=False))
        return

    if commit:
        os.makedirs(os.path.dirname(STATE), exist_ok=True)
        mark = {"i": n.get("i"), "played": n.get("played"), "done": bool(n.get("done")),
                "at": datetime.now(timezone.utc).isoformat()}
        io.open(STATE, "w", encoding="utf-8").write(json.dumps(mark, ensure_ascii=False))
        print(json.dumps({"committed": mark}, ensure_ascii=False))
        return

    news, why = decide(n, load_state())
    out = {"news": news, "why": why, "num": n.get("num"), "played": n.get("played"),
           "total": n.get("total"), "done": n.get("done")}
    if news:
        out["message"] = message(n)
        out["text"] = n.get("text") or ""
    print(json.dumps(out, ensure_ascii=False))


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    main()
