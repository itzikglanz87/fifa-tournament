/* ============================================================================
   The push server — two jobs, nothing else.

   1. onResultSaved   A tournament document changed. If the number of results
                      went UP, send everyone "the next match" — and, first, a
                      "⚡ peak moment" when that league result swung someone's
                      chance of reaching the final by 30+ points or settled it
                      (peak.js, on the app's own odds model via model.js).
                      Whoever entered the result, the server sends it — so any
                      friend can fill in scores, and nobody's phone needs a key.

   2. adminPush       A message written by the admin. Refused unless the call
                      carries ADMIN_KEY, which lives only in functions/.env
                      (never committed) and on the admin's own phone.
                      With `story` (a newsroom card), the card is saved as it
                      is at that moment in stories/{id}, and a tap on the
                      push opens the app on exactly that card.

   Tokens: each phone that enables notifications writes pushTokens/{token}.
   Tokens that Firebase reports as dead are deleted after every send.
   ========================================================================= */
"use strict";

const { onDocumentWritten } = require("firebase-functions/v2/firestore");
const { onCall, HttpsError } = require("firebase-functions/v2/https");
const { setGlobalOptions } = require("firebase-functions/v2");
const { defineString } = require("firebase-functions/params");
/* firebase-admin 13+ is modular only: admin.firestore()/admin.messaging()
   no longer exist */
const { initializeApp } = require("firebase-admin/app");
const { getFirestore } = require("firebase-admin/firestore");
const { getMessaging } = require("firebase-admin/messaging");
const T = require("./tournament");
const { peakOf } = require("./peak");

initializeApp();
const db = getFirestore();

/* The Firestore trigger must run where the database lives. Set from
   `firebase firestore:databases:get` before the first deploy; the app reads
   the same value from FUNCTIONS_REGION in firebase-config.js. */
const REGION = "europe-west1";
setGlobalOptions({ region: REGION, maxInstances: 3 });

const ADMIN_KEY = defineString("ADMIN_KEY");
const APP_URL = "https://itzikglanz87.github.io/fifa-tournament/";

async function seasonName(season) {
  try {
    const cfg = await db.doc("meta/config").get();
    const s = ((cfg.data() || {}).seasons || []).find(x => x.id === season);
    return s ? s.name : "";
  } catch (e) { return ""; }
}

/* Send to every registered phone (or one token), prune the dead ones. */
async function sendToAll(title, body, onlyToken, url) {
  let tokens;
  if (onlyToken) tokens = [onlyToken];
  else tokens = (await db.collection("pushTokens").get()).docs.map(d => d.id);
  if (!tokens.length) return { sent: 0, failed: 0, phones: 0 };

  let sent = 0, failed = 0;
  for (let i = 0; i < tokens.length; i += 500) {
    const batch = tokens.slice(i, i + 500);
    /* data-only: the app's own service worker draws the notification, so it
       looks the same whether the app is open, in the background or closed */
    const res = await getMessaging().sendEachForMulticast({
      tokens: batch,
      data: { title: String(title || ""), body: String(body || ""), url: url || APP_URL },
      webpush: { headers: { Urgency: "high", TTL: "86400" } }
    });
    sent += res.successCount; failed += res.failureCount;
    const dead = [];
    res.responses.forEach((r, k) => {
      const code = r.error && r.error.code;
      if (code === "messaging/registration-token-not-registered" ||
          code === "messaging/invalid-registration-token" ||
          code === "messaging/invalid-argument") dead.push(batch[k]);
    });
    await Promise.all(dead.map(t => db.doc("pushTokens/" + t).delete().catch(() => {})));
  }
  return { sent, failed, phones: tokens.length };
}

/* ---------------------------------------------------------------- 1. auto */
exports.onResultSaved = onDocumentWritten("tournaments/{id}", async event => {
  const id = event.params.id;
  const logRef = db.doc("pushLog/" + id);
  const before = event.data.before.exists ? T.unpack(event.data.before.data()) : null;
  const after = event.data.after.exists ? T.unpack(event.data.after.data()) : null;

  /* a deleted tournament forgets its log; a new one starts from zero, so an
     id reused after a delete is not muted by the old tournament's count */
  if (!after) { await logRef.delete().catch(() => {}); return; }
  if (!before) { await logRef.set({ progress: T.progressOf(after), at: new Date().toISOString() }); return; }

  const now = T.progressOf(after);
  if (now <= T.progressOf(before)) return;                  // a correction or a clear

  /* Triggers can fire more than once, and a result can be cleared and typed
     again; the log makes sure each step forward is announced exactly once. */
  const go = await db.runTransaction(async tx => {
    const log = await tx.get(logRef);
    const last = log.exists ? (log.data().progress || 0) : T.progressOf(before);
    if (now <= last) return false;
    tx.set(logRef, { progress: now, at: new Date().toISOString() });
    return true;
  });
  if (!go) return;

  /* a peak moment first — a league result that swung someone's road to the
     final. It runs the app's own odds model; if anything in it fails, the
     next-match push below still goes out. */
  try {
    const cfg = await db.doc("meta/config").get();
    const recs = (await db.collection("tournaments").get()).docs.map(d => T.unpack(d.data()));
    const pk = peakOf(before, after, recs, (cfg.data() || {}).seasons);
    if (pk) {
      const r = await sendToAll("⚡ רגע שיא · טורניר " + (after.n || after.i), pk.text);
      console.log("peak push", id, now, JSON.stringify(r), pk.text, "swing", pk.swing.toFixed(2));
    }
  } catch (e) {
    console.error("peak moment skipped:", e && e.stack || e);
  }

  const body = T.nextEventText(after);
  if (!body) return;
  const title = "טורניר " + (after.n || after.i) + " · " + (await seasonName(after.s));
  const r = await sendToAll(title, body);
  console.log("auto push", id, now, JSON.stringify(r), body);
});

/* A newsroom card, frozen as the admin sent it. Only known fields, only
   plain values, and a size cap: the key holder is trusted, but a malformed
   call should not put junk in the store. */
async function saveStory(s) {
  const str = (v, n) => String(v == null ? "" : v).slice(0, n);
  const num = v => (typeof v === "number" && isFinite(v) ? v : null);
  const doc = {
    tag: str(s.tag, 60), head: str(s.head, 600), body: str(s.body, 24000), plain: str(s.plain, 4000),
    icon: str(s.icon, 8), who: Array.isArray(s.who) ? s.who.filter(x => typeof x === "number").slice(0, 6) : [],
    num: num(s.num), season: str(s.season, 60), played: num(s.played), total: num(s.total),
    at: new Date().toISOString()
  };
  if (!doc.head.trim()) throw new HttpsError("invalid-argument", "לכתבה אין כותרת");
  const id = Date.now().toString(36) + Math.random().toString(36).slice(2, 8);
  await db.doc("stories/" + id).set(doc);
  return id;
}

/* --------------------------------------------------------------- 2. admin */
exports.adminPush = onCall(async req => {
  const d = req.data || {};
  const key = ADMIN_KEY.value();
  if (!key || typeof d.key !== "string" || d.key !== key) {
    throw new HttpsError("permission-denied", "מפתח אדמין שגוי");
  }
  if (d.check) return { ok: true };                          // "is this key right?"
  const title = String(d.title || "טורניר פיפא").slice(0, 80);
  const body = String(d.body || "").slice(0, 400);
  if (!body.trim()) throw new HttpsError("invalid-argument", "ההודעה ריקה");
  let url = null, storyId = null;
  if (d.story) {
    storyId = await saveStory(d.story);
    url = APP_URL + "#story=" + storyId;
  }
  const r = await sendToAll(title, body, typeof d.token === "string" ? d.token : null, url);
  console.log("admin push", JSON.stringify(r), title, body, storyId || "");
  return Object.assign({ ok: true, story: storyId }, r);
});
