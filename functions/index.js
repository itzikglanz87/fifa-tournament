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
const { makeKit } = require("./model");
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
/* tag: a later push with the same tag replaces the earlier one on the phone
   (the poll and its reminders), instead of piling up */
async function sendToAll(title, body, onlyToken, url, tag) {
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
      data: Object.assign({ title: String(title || ""), body: String(body || ""), url: url || APP_URL },
                          tag ? { tag: String(tag).slice(0, 40) } : {}),
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

/* A prediction window: the players sitting the match out, and 3 minutes
   from the push (plus a few seconds for delivery). The database rules read
   this document, so a late or wrong-player prediction is refused there, not
   just hidden by the app. Opened once per match: a result cleared and typed
   again does not reopen it. */
const PRED_MS = 3 * 60e3 + 5e3;
async function openPredWindow(docId, rec, nx) {
  const tid = rec.s ? rec.s * 1000 + (rec.n || rec.i) : (rec.n || rec.i);
  const ref = db.doc("predWindows/" + tid + "_" + nx.k);
  const now = Date.now();
  return db.runTransaction(async tx => {
    const s = await tx.get(ref);
    if (s.exists) return false;
    tx.set(ref, { t: tid, k: nx.k, sit: nx.sit, open: new Date(now), close: new Date(now + PRED_MS), closeMs: now + PRED_MS });
    return true;
  });
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
  if (!before) {
    await logRef.set({ progress: T.progressOf(after), at: new Date().toISOString() });
    /* a new tournament: its first match has no result before it to announce
       it, so the opening itself does — and opens the first prediction window */
    const first = T.nextLeagueMatch(after);
    if (first && first.k === 0) {
      await openPredWindow(id, after, first);
      const title = "🏆 טורניר " + (after.n || after.i) + " נפתח · " + (await seasonName(after.s));
      const r = await sendToAll(title, T.nextEventText(after) + T.predLine(first.sit));
      console.log("opening push", id, JSON.stringify(r));
    }
    return;
  }

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

  /* new achievements this result unlocked — the same list the player page
     shows, run on the store before and after the change */
  try {
    const cfg = await db.doc("meta/config").get();
    const seasons = (cfg.data() || {}).seasons;
    const docs = (await db.collection("tournaments").get()).docs;
    const recsAfter = docs.map(d => T.unpack(d.data()));
    const recsBefore = docs.map(d => d.id === id ? before : T.unpack(d.data()));
    const nb = makeKit(recsBefore, seasons).achievements(), K = makeKit(recsAfter, seasons), na = K.achievements();
    const lines = [];
    Object.keys(na).forEach(p => Object.keys(na[p]).forEach(aid => {
      if (!nb[p][aid]) { const a = K.ACH.find(x => x.id === aid); if (a) lines.push(T.P[p] + " — " + a.icon + " " + a.name); }
    }));
    if (lines.length && lines.length <= 6) {
      const r = await sendToAll("🏅 הישג חדש · טורניר " + (after.n || after.i), lines.join("\n"));
      console.log("achievement push", id, JSON.stringify(r), lines.join(" | "));
    }
  } catch (e) {
    console.error("achievements skipped:", e && e.stack || e);
  }

  let body = T.nextEventText(after);
  if (!body) return;
  /* the next league match opens its prediction window with this push */
  const nx = T.nextLeagueMatch(after);
  if (nx && await openPredWindow(id, after, nx)) body += T.predLine(nx.sit);
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
function requireAdmin(d) {
  const key = ADMIN_KEY.value();
  if (!key || !d || typeof d.key !== "string" || d.key !== key) {
    throw new HttpsError("permission-denied", "מפתח אדמין שגוי");
  }
}

exports.adminPush = onCall(async req => {
  const d = req.data || {};
  requireAdmin(d);
  if (d.check) return { ok: true };                          // "is this key right?"
  const title = String(d.title || "טורניר פיפא").slice(0, 80);
  const body = String(d.body || "").slice(0, 400);
  if (!body.trim()) throw new HttpsError("invalid-argument", "ההודעה ריקה");
  let url = null, storyId = null;
  if (d.open === "poll") url = APP_URL + "#poll";
  if (d.story) {
    storyId = await saveStory(d.story);
    url = APP_URL + "#story=" + storyId;
  }
  const r = await sendToAll(title, body, typeof d.token === "string" ? d.token : null, url,
                           typeof d.tag === "string" ? d.tag : null);
  console.log("admin push", JSON.stringify(r), title, body, storyId || "");
  return Object.assign({ ok: true, story: storyId }, r);
});

/* --------------------------------------------------------- 3. the camera */
/* The scoreboard reader on the computer sends what it read off the screen.
   It never picks a match: it updates whichever match the app has open as
   live, and only upwards (a replay or a misread cannot take goals away). */
exports.liveScore = onCall(async req => {
  const d = req.data || {};
  requireAdmin(d);
  /* the reader checks in: is it wanted right now, and is a match open?
     Its visit is remembered so the app can say whether the computer is up. */
  if (d.ping) {
    const ref = db.doc("meta/camera");
    const cur = (await ref.get()).data() || {};
    const on = cur.on !== false;
    await ref.set(Object.assign({}, cur, { on, seen: new Date().toISOString() }));
    const open = (await db.collection("live").get()).docs;
    const one = open.length ? open[0].data() : null;
    return { on, live: !!one, h: one ? one.h : null, a: one ? one.a : null };
  }
  let h = Math.max(0, Math.min(30, Math.round(Number(d.h))));
  let a = Math.max(0, Math.min(30, Math.round(Number(d.a))));
  if (!isFinite(h) || !isFinite(a)) throw new HttpsError("invalid-argument", "תוצאה לא תקינה");
  const docs = (await db.collection("live").get()).docs;
  if (!docs.length) return { live: false };
  let ref = docs[0].ref, cur = docs[0].data() || {};
  if (d.check) return { live: true, h: cur.h, a: cur.a, t: cur.t, k: cur.k };

  /* the scoreboard also says which clubs are playing. If that is a different
     fixture than the one the app opened — they decided to play match 4 before
     match 3 — move the live match there, and swap the score when the sides
     are the other way round. */
  let swap = false, moved = null;
  if (d.clubs && d.clubs.h && d.clubs.a) {
    const snap = await db.doc("tournaments/t" + cur.t).get();
    if (snap.exists) {
      const rec = T.unpack(snap.data());
      const der = T.derive(rec);
      const same = (x, y) => String(x || "").trim() === String(y || "").trim();
      /* the same two clubs can meet twice in one tournament, so the clubs
         alone are not always enough: stay on the fixture the app opened when
         it fits, otherwise take the earliest unplayed one that does */
      const fits = der.m.filter(m => !(m.s && m.s[0] != null && m.s[1] != null) &&
        ((same(m.hc, d.clubs.h) && same(m.ac, d.clubs.a)) || (same(m.hc, d.clubs.a) && same(m.ac, d.clubs.h))));
      const hit = fits.find(m => m.i === cur.k) || fits[0];
      if (hit && hit.i !== cur.k) {
        moved = hit.i;
        const fresh = { t: cur.t, k: hit.i, h: 0, a: 0, startAt: cur.startAt || new Date().toISOString() };
        if (!cur.h && !cur.a) await ref.delete().catch(() => {});   // nothing was scored yet
        ref = db.doc("live/" + cur.t + "_" + hit.i);
        cur = Object.assign(fresh, (await ref.get()).data() || {});
      }
      if (hit && same(hit.hc, d.clubs.a)) swap = true;
    }
  }
  if (swap) { const t2 = h; h = a; a = t2; }
  if (h < (cur.h || 0) || a < (cur.a || 0)) return { live: true, h: cur.h, a: cur.a, ignored: "lower" };
  if (h === cur.h && a === cur.a) return { live: true, h: cur.h, a: cur.a, same: true };
  await ref.set(Object.assign({}, cur, { h, a, at: new Date().toISOString(), src: "cam", by: -1 }));
  console.log("cam score", cur.t + "_" + cur.k, cur.h + "-" + cur.a, "->", h + "-" + a, moved != null ? "(moved to match " + (moved + 1) + ")" : "");
  return { live: true, h, a, updated: true, k: cur.k, moved };
});

/* ------------------------------------------------------------ 4. activity */
/* The activity log: each phone writes visits/{id} when the app opens (the
   rules let it create, never read). Only the admin reads it, through here. */
exports.adminVisits = onCall(async req => {
  const d = req.data || {};
  requireAdmin(d);
  const days = Math.max(1, Math.min(400, Number(d.days) || 30));
  const since = new Date(Date.now() - days * 864e5).toISOString();
  const snap = await db.collection("visits").where("at", ">=", since).orderBy("at", "desc").limit(5000).get();
  return {
    days,
    visits: snap.docs.map(x => {
      const v = x.data() || {};
      return { who: typeof v.who === "number" ? v.who : null, at: v.at, dev: v.dev || "", app: v.app || "" };
    })
  };
});
