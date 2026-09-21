/* ============================================================================
   The push server — two jobs, nothing else.

   1. onResultSaved   A tournament document changed. If the number of results
                      went UP, send everyone "the next match". Whoever entered
                      the result, the server sends it — so any friend can fill
                      in scores, and nobody's phone needs a key to push.

   2. adminPush       A message written by the admin. Refused unless the call
                      carries ADMIN_KEY, which lives only in functions/.env
                      (never committed) and on the admin's own phone.

   Tokens: each phone that enables notifications writes pushTokens/{token}.
   Tokens that Firebase reports as dead are deleted after every send.
   ========================================================================= */
"use strict";

const { onDocumentWritten } = require("firebase-functions/v2/firestore");
const { onCall, HttpsError } = require("firebase-functions/v2/https");
const { setGlobalOptions } = require("firebase-functions/v2");
const { defineString } = require("firebase-functions/params");
const admin = require("firebase-admin");
const T = require("./tournament");

admin.initializeApp();
const db = admin.firestore();

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
async function sendToAll(title, body, onlyToken) {
  let tokens;
  if (onlyToken) tokens = [onlyToken];
  else tokens = (await db.collection("pushTokens").get()).docs.map(d => d.id);
  if (!tokens.length) return { sent: 0, failed: 0, phones: 0 };

  let sent = 0, failed = 0;
  for (let i = 0; i < tokens.length; i += 500) {
    const batch = tokens.slice(i, i + 500);
    /* data-only: the app's own service worker draws the notification, so it
       looks the same whether the app is open, in the background or closed */
    const res = await admin.messaging().sendEachForMulticast({
      tokens: batch,
      data: { title: String(title || ""), body: String(body || ""), url: APP_URL },
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

  const body = T.nextEventText(after);
  if (!body) return;
  const title = "טורניר " + (after.n || after.i) + " · " + (await seasonName(after.s));
  const r = await sendToAll(title, body);
  console.log("auto push", id, now, JSON.stringify(r), body);
});

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
  const r = await sendToAll(title, body, typeof d.token === "string" ? d.token : null);
  console.log("admin push", JSON.stringify(r), title, body);
  return Object.assign({ ok: true }, r);
});
