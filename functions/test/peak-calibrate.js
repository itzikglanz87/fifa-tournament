/* How often would each threshold fire? Replays all archive tournaments,
   result by result in fixture order, and counts the peak moments per
   tournament at a range of swing thresholds.    node functions/test/peak-calibrate.js */
"use strict";
const { makeKit } = require("../model");
const SEED = require("../seed.json");

const K = makeKit([], []);
const swings = [], perT = [];
let clinches = 0, outs = 0;
SEED.T.forEach((t, n) => {
  const size = t.d.length;
  const slots = t.d.map(x => x[0]);
  const clubs = t.d.map(x => SEED.C[x[1]]);
  /* the archive stores matches expanded; rebuild a record in template order */
  const tpl = SEED.TPL[String(size)];
  const scores = tpl.map((f, k) => {
    const hm = t.m.find(m => m[0] === slots[f.h[0] - 1] && m[1] === slots[f.h[1] - 1] &&
                             m[3] === slots[f.a[0] - 1] && m[4] === slots[f.a[1] - 1]);
    return hm ? [hm[6], hm[7]] : null;
  });
  if (scores.some(s => !s)) return;                        // an early, non-template tournament
  let rec = { i: 5000 + n, s: 0, n: t.i, tpl: String(size), slots, clubs,
              scores: tpl.map(() => [null, null]), champs: [] };
  const mine = [];
  for (let k = 0; k < scores.length; k++) {
    const before = JSON.parse(JSON.stringify(rec));
    rec.scores[k] = scores[k];
    const tb = K.decorate(K.hydrate(JSON.parse(JSON.stringify(before))));
    const ta = K.decorate(K.hydrate(JSON.parse(JSON.stringify(rec))));
    const seed = (Math.imul(ta.i, 2654435761) ^ 0x5f3a) >>> 0;
    const A = K.simulate(tb, 4000, null, seed), B = K.simulate(ta, 4000, null, seed);
    let best = 0, from = 0, to = 0;
    ta.players.forEach(p => { const d = Math.abs(B[p].top4 - A[p].top4); if (d > best) { best = d; from = A[p].top4; to = B[p].top4; } });
    const cl = to >= 0.995 && from < 0.95, ou = to <= 0.005 && from > 0.05;
    if (cl) clinches++; if (ou) outs++;
    mine.push({ swing: best, fate: cl || ou });
    swings.push(best);
  }
  perT.push(mine);
});

console.log("tournaments replayed:", perT.length, "· results:", swings.length);
console.log("fate-settling results (a final place made certain or lost):", clinches + outs,
            "(" + (clinches + outs) / perT.length + " per tournament)");
for (const th of [0.20, 0.25, 0.30, 0.35, 0.40]) {
  const counts = perT.map(ms => ms.filter(x => x.swing >= th || x.fate).length);
  const avg = counts.reduce((a, b) => a + b, 0) / counts.length;
  const none = counts.filter(c => c === 0).length;
  console.log("threshold " + th.toFixed(2) + ": " + avg.toFixed(2) + " peak pushes per tournament · " +
              none + " tournaments with none · max " + Math.max(...counts));
}
const sorted = swings.slice().sort((a, b) => a - b);
console.log("swing quantiles: median " + sorted[Math.floor(sorted.length / 2)].toFixed(2) +
            " · 90% " + sorted[Math.floor(sorted.length * 0.9)].toFixed(2));
