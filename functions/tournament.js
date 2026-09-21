/* ============================================================================
   The tournament rules, as the server needs them to write a push.

   This mirrors the app (src/p2.html decorate/finalLegs/applyFinal and
   src/p4.html progressOf/nextEventText) and is tested against it in
   functions/test/parity.js — change one, run the test, change the other.
   The fixture templates and player names are not copied by hand: build.py
   writes them into data.json from the same src/data2.json the app ships.
   ========================================================================= */
"use strict";

const DATA = require("./data.json");
const P = DATA.P;
const TPL = DATA.TPL;

/* Firestore refuses nested arrays, so db.js stores [[h,a],...] as
   [{__a:[h,a]},...]. Undo it the same way. */
function unpack(v) {
  if (Array.isArray(v)) return v.map(unpack);
  if (v && typeof v === "object") {
    const keys = Object.keys(v);
    if (keys.length === 1 && keys[0] === "__a" && Array.isArray(v.__a)) return unpack(v.__a);
    const o = {};
    keys.forEach(k => { o[k] = unpack(v[k]); });
    return o;
  }
  return v;
}

const played = s => Array.isArray(s) && s[0] != null && s[1] != null;

/* The record -> fixtures, standings and the two final legs. Club names stay
   names (the record stores them that way); the app maps them to indexes. */
function derive(rec) {
  const slots = rec.slots || [], clubs = rec.clubs || [];
  const tpl = TPL[rec.tpl] || TPL[String(slots.length)] || [];
  const teamOf = {};
  slots.forEach((p, i) => { teamOf[p] = clubs[i]; });

  const m = tpl.map((f, k) => {
    const sc = (rec.scores && rec.scores[k]) || [null, null];
    return { i: k, h: [slots[f.h[0] - 1], slots[f.h[1] - 1]], hc: clubs[f.hc - 1],
             a: [slots[f.a[0] - 1], slots[f.a[1] - 1]], ac: clubs[f.ac - 1], s: sc };
  });

  const acc = {};
  slots.forEach(p => { acc[p] = { pts: 0, gf: 0, ga: 0 }; });
  m.forEach(x => {
    if (!played(x.s)) return;
    const [hg, ag] = x.s;
    const hp = hg === ag ? 1 : hg > ag ? 3 : 0, ap = hg === ag ? 1 : ag > hg ? 3 : 0;
    x.h.forEach(p => { acc[p].pts += hp; acc[p].gf += hg; acc[p].ga += ag; });
    x.a.forEach(p => { acc[p].pts += ap; acc[p].gf += ag; acc[p].ga += hg; });
  });
  /* same order as the app: points, goal difference, goals scored; ties keep
     the draw order (Array.prototype.sort is stable) */
  const table = slots.slice().sort((a, b) =>
    acc[b].pts - acc[a].pts || (acc[b].gf - acc[b].ga) - (acc[a].gf - acc[a].ga) || acc[b].gf - acc[a].gf);

  let legs = null;
  if (table.length >= 4) {
    const sc = rec.final || [[null, null], [null, null]];
    const g = i => (sc[i] && sc[i].length === 2) ? sc[i] : [null, null];
    legs = [
      { home: [table[2], table[3]], hc: teamOf[table[3]], away: [table[0], table[1]], ac: teamOf[table[1]], s: g(0) },
      { home: [table[0], table[1]], hc: teamOf[table[0]], away: [table[2], table[3]], ac: teamOf[table[2]], s: g(1) }
    ];
  }

  let champs = (rec.champs || []).slice();
  if (rec.final && legs) {
    if (!legs.every(l => played(l.s))) champs = [];
    else {
      const top = legs[0].s[1] + legs[1].s[0], bot = legs[0].s[0] + legs[1].s[1];
      if (top > bot) champs = [table[0], table[1]];
      else if (bot > top) champs = [table[2], table[3]];
      else champs = rec.gg ? (rec.champs || []).slice() : [];
    }
  }
  return { m, table, legs, champs, teamOf };
}

/* results so far: group matches + final legs + a decided champion */
function progressOf(rec) {
  const d = derive(rec);
  const g = d.m.filter(x => played(x.s)).length;
  const legs = (rec.final && d.legs) ? d.legs.filter(l => played(l.s)).length : 0;
  const champ = (rec.final && d.champs.length === 2) ? 1 : 0;
  return g + legs + champ;
}

const pair = (a, b) => P[a] + " ו" + P[b];

function nextEventText(rec) {
  const d = derive(rec);
  const nx = d.m.find(x => !played(x.s));
  if (nx) {
    return "המשחק הבא - מחזור " + (nx.i + 1) + ", " + pair(nx.h[0], nx.h[1]) + " בבית עם " + nx.hc +
           " נגד " + pair(nx.a[0], nx.a[1]) + " בחוץ עם " + nx.ac;
  }
  if (!d.legs) return null;
  const k = d.legs.findIndex(l => !played(l.s));
  if (k >= 0) {
    const L = d.legs[k];
    return (k === 0 ? "שלב הליגה הסתיים! " : "") + "הגמר - משחק " + (k + 1) + " מתוך 2, " +
           pair(L.home[0], L.home[1]) + " בבית עם " + L.hc +
           " נגד " + pair(L.away[0], L.away[1]) + " בחוץ עם " + L.ac;
  }
  if (d.champs.length === 2) return "טורניר " + (rec.n || rec.i) + " הסתיים! האלופים: " + pair(d.champs[0], d.champs[1]);
  return "הגמר נגמר בשוויון - מי ניצח בשער הזהב?";
}

/* the next league match, and who sits it out — the only ones who may
   predict it (two of six, one of five) */
function nextLeagueMatch(rec) {
  const d = derive(rec);
  const nx = d.m.find(x => !played(x.s));
  if (!nx) return null;
  const on = new Set([nx.h[0], nx.h[1], nx.a[0], nx.a[1]]);
  return { k: nx.i, sit: (rec.slots || []).filter(p => !on.has(p)) };
}
const predLine = sit => sit.length ? "\n🔮 " + sit.map(p => P[p]).join(" ו") + " — יש לכם 3 דקות לנחש!" : "";

module.exports = { unpack, derive, progressOf, nextEventText, nextLeagueMatch, predLine, P, TPL };
