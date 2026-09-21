/* ============================================================================
   The trigger's decisions, against an in-memory stand-in for Firebase.

   Real Firestore and FCM are replaced by fakes, so this checks only what
   index.js DECIDES: a new result sends once, a correction or a clear sends
   nothing, a trigger delivered twice sends once, a deleted-and-recreated
   tournament is not muted by the old one, and the admin call refuses a wrong
   key.       node functions/test/trigger.js
   ========================================================================= */
"use strict";
const Module = require("module");

/* ---------------------------------------------------------- fake firebase */
const store = {};                       // path -> data
const sent = [];                        // what "FCM" was asked to deliver
const snap = (path) => ({ exists: path in store, id: path.split("/").pop(), data: () => store[path] });
const docRef = path => ({
  path,
  get: async () => snap(path),
  set: async d => { store[path] = JSON.parse(JSON.stringify(d)); },
  delete: async () => { delete store[path]; }
});
const fakeAdmin = {
  initializeApp() {},
  firestore: () => ({
    doc: docRef,
    collection: name => ({ get: async () => ({ docs: Object.keys(store).filter(p => p.startsWith(name + "/")).map(snap) }) }),
    runTransaction: async fn => fn({ get: r => r.get(), set: (r, d) => r.set(d) })
  }),
  messaging: () => ({
    sendEachForMulticast: async msg => {
      sent.push({ title: msg.data.title, body: msg.data.body, to: msg.tokens.length });
      return { successCount: msg.tokens.length, failureCount: 0, responses: msg.tokens.map(() => ({ success: true })) };
    }
  })
};
const load = Module._load;
Module._load = function (req) { return req === "firebase-admin" ? fakeAdmin : load.apply(this, arguments); };
process.env.ADMIN_KEY = "right-key";
process.env.GCLOUD_PROJECT = "analytics-2bf94";
const F = require("../index.js");

/* --------------------------------------------------------------- helpers */
const pack = rec => JSON.parse(JSON.stringify(rec, (k, v) =>
  Array.isArray(v) ? v.map(e => Array.isArray(e) ? { __a: e } : e) : v));
const change = async (id, before, after) => {
  const path = "tournaments/" + id;
  const b = before ? pack(before) : null, a = after ? pack(after) : null;
  if (a) store[path] = a; else delete store[path];
  await F.onResultSaved.run({
    params: { id },
    data: { before: { exists: !!b, data: () => b }, after: { exists: !!a, data: () => a } }
  });
};
let fails = 0;
const expect = (label, cond, extra) => { console.log((cond ? "  ok   " : "  FAIL ") + label + (extra ? "  — " + extra : "")); if (!cond) fails++; };

(async () => {
  store["meta/config"] = { seasons: [{ id: 1, name: "עונת 2027" }] };
  store["pushTokens/phoneA"] = { token: "phoneA" };
  store["pushTokens/phoneB"] = { token: "phoneB" };

  const base = { i: 1001, s: 1, n: 1, tpl: "6", slots: [1, 3, 0, 5, 4, 2],
    clubs: ["באיירן", "פסז", "ליברפול", "סיטי", "ריאל", "ברצלונה"],
    scores: Array.from({ length: 12 }, () => [null, null]), champs: [] };
  const withScores = (rec, pairs) => { const r = JSON.parse(JSON.stringify(rec)); pairs.forEach(([k, s]) => { r.scores[k] = s; }); return r; };

  await change("t1001", null, base);
  expect("opening a tournament sends nothing", sent.length === 0);

  const r1 = withScores(base, [[0, [1, 0]]]);
  await change("t1001", base, r1);
  expect("a new result sends one push", sent.length === 1, sent[0] && sent[0].body);
  expect("…to every registered phone", sent[0] && sent[0].to === 2);
  expect("…titled with the tournament and season", sent[0] && sent[0].title === "טורניר 1 · עונת 2027", sent[0] && sent[0].title);

  await change("t1001", base, r1);
  expect("the same trigger delivered twice sends once", sent.length === 1);

  const r1b = withScores(base, [[0, [3, 0]]]);
  await change("t1001", r1, r1b);
  expect("correcting a score sends nothing", sent.length === 1);

  await change("t1001", r1b, base);
  expect("clearing a result sends nothing", sent.length === 1);
  await change("t1001", base, r1b);
  expect("typing it back after a clear does not repeat the push", sent.length === 1);

  const r2 = withScores(r1b, [[1, [2, 2]]]);
  await change("t1001", r1b, r2);
  expect("the next new result sends again", sent.length === 2, sent[1] && sent[1].body);

  await change("t1001", r2, null);
  expect("deleting the tournament clears its log", !("pushLog/t1001" in store));
  await change("t1001", null, base);
  await change("t1001", base, r1);
  expect("a recreated tournament with the same id is not muted", sent.length === 3);

  /* the admin door */
  const call = data => F.adminPush.run({ data, auth: null, rawRequest: {} });
  let refused = false;
  try { await call({ key: "wrong", body: "x" }); } catch (e) { refused = e.code === "permission-denied"; }
  expect("a wrong admin key is refused", refused);
  const ok = await call({ key: "right-key", check: true });
  expect("the right key passes the check without sending", ok.ok === true && sent.length === 3);
  const r = await call({ key: "right-key", title: "הודעה", body: "מחר ב־8" });
  expect("the admin message goes to everyone", sent.length === 4 && sent[3].to === 2 && r.sent === 2, sent[3] && sent[3].body);
  await call({ key: "right-key", body: "בדיקה", token: "phoneA" });
  expect("a test message goes to one phone only", sent[4] && sent[4].to === 1);

  console.log("\n" + (fails ? fails + " FAILED" : "all passed"));
  process.exit(fails ? 1 : 0);
})().catch(e => { console.error(e); process.exit(1); });
