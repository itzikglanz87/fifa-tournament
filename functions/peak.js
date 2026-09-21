/* ============================================================================
   "A peak moment": a league result that swung someone's road to the final.

   The app's own model (model.js) simulates the tournament just before and
   just after the new result, from one pinned seed, so the difference is the
   result and not the dice. The player whose chance of reaching the final
   moved most is the story. It is a peak moment when that move is big, or
   when it settles his fate outright (a place in the final made certain, or
   lost for good).

   League stage only: once the league is over the four finalists are fixed,
   and the simulation does not condition on a final leg already played, so
   its title odds between the legs would not mean anything.
   ========================================================================= */
"use strict";
const { makeKit } = require("./model");

const BIG_SWING = 0.30;          // calibrated on the archive: see test/peak-calibrate.js
const played = s => Array.isArray(s) && s[0] != null && s[1] != null;
const clone = o => JSON.parse(JSON.stringify(o));

/* which league match did this write complete? */
function newLeagueResult(before, after) {
  const a = after.scores || [], b = before.scores || [];
  for (let k = 0; k < a.length; k++) if (played(a[k]) && !played(b[k])) return k;
  return -1;
}

function peakOf(before, after, allRecs, seasons, kit) {
  const k = newLeagueResult(before, after);
  if (k < 0) return null;                                  // a correction, or a final leg
  const K = kit || makeKit(allRecs, seasons);
  const tb = K.decorate(K.hydrate(clone(before)));
  const ta = K.decorate(K.hydrate(clone(after)));
  const seed = (Math.imul(ta.i, 2654435761) ^ 0x5f3a) >>> 0;
  const A = K.simulate(tb, 4000, null, seed), B = K.simulate(ta, 4000, null, seed);
  if (!A || !B) return null;

  let who = null, from = 0, to = 0;
  ta.players.forEach(p => {
    const d = B[p].top4 - A[p].top4;
    if (!who || Math.abs(d) > Math.abs(to - from)) { who = p; from = A[p].top4; to = B[p].top4; }
  });
  const clinched = to >= 0.995 && from < 0.95;
  const out = to <= 0.005 && from > 0.05;
  const swing = Math.abs(to - from);
  if (!clinched && !out && swing < BIG_SWING) return null;

  const m = ta.m[k];
  const pair = (x, y) => K.P[x] + " ו" + K.P[y];
  const game = pair(m[0], m[1]) + " " + m[6] + ":" + m[7] + " " + pair(m[3], m[4]);
  const pct = x => Math.round(x * 100) + "%";
  let text;
  if (clinched) text = K.P[who] + " הבטיח מקום בגמר! אחרי " + game;
  else if (out) text = K.P[who] + " נפרד מהגמר אחרי " + game;
  else text = K.P[who] + (to > from ? " קפץ" : " צנח") + " מ־" + pct(from) + " ל־" + pct(to) +
              " סיכוי לעלות לגמר אחרי " + game;
  return { who, from, to, swing, clinched, out, match: k, text };
}

module.exports = { peakOf, newLeagueResult, BIG_SWING };
