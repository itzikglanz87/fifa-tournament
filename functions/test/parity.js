/* ============================================================================
   Parity: the push server must read a tournament exactly the way the app does.

   Loads the app's OWN rules out of the built index.html (hydrate, decorate,
   finalLegs, applyFinal, nextFixture) and compares them with
   functions/tournament.js over many random tournaments — six players and
   five, played out in random order, through both final legs, including level
   aggregates settled by the golden goal.

       node functions/test/parity.js        (after python src/build.py)
   ========================================================================= */
"use strict";
const fs = require("fs"), path = require("path"), vm = require("vm");
const T = require("../tournament");

const html = fs.readFileSync(path.join(__dirname, "..", "..", "index.html"), "utf8").split(String.fromCharCode(13)).join("");
const i = html.indexOf("\n<script>\n") + "\n<script>\n".length;
const script = html.slice(i, html.indexOf("</script>", i));
const seedJson = (() => {
  const k = html.indexOf('<script id="seed" type="application/json">');
  const a = html.indexOf(">", k) + 1;
  return html.slice(a, html.indexOf("</script>", a));
})();
const grab = (from, to) => {
  const a = script.indexOf(from), b = script.indexOf(to, a + 1);
  if (a < 0 || b < 0) throw new Error("marker not found: " + (a < 0 ? from : to));
  return script.slice(a, b);
};

const code = [
  "const SEED = " + seedJson + ";",
  "const PHOTOS = {};",
  grab("const P = SEED.P", "function computeOVR"),     // model, decorate, finalLegs, applyFinal
  grab("function hydrate(rec)", "function paintRows()"),
  grab("function nextFixture(t)", "function lastPlayed(t)"),
  "this.app = { hydrate, decorate, nextFixture, CLUBS, P };"
].join("\n");
const ctx = { console, document: undefined, window: {} };
vm.createContext(ctx);
vm.runInContext(code, ctx);
const A = ctx.app;

/* ------------------------------------------------------------- the model */
let seed = 12345;
const rnd = () => { seed = (seed * 1103515245 + 12345) & 0x7fffffff; return seed / 0x7fffffff; };
const goals = () => Math.floor(rnd() * rnd() * 6);
const shuffle = a => { for (let k = a.length - 1; k > 0; k--) { const j = Math.floor(rnd() * (k + 1)); [a[k], a[j]] = [a[j], a[k]]; } return a; };
const RING = ["ריאל", "באיירן", "ליברפול", "סיטי", "פסז", "ברצלונה"];

function appView(rec) {
  const t = A.decorate(A.hydrate(JSON.parse(JSON.stringify(rec))));
  const nx = A.nextFixture(t);
  return {
    table: t.table.join(","),
    next: nx ? nx.i : -1,
    legs: t.legs ? t.legs.map(l => [l.home.join("+"), A.CLUBS[l.hc], l.away.join("+"), A.CLUBS[l.ac]].join("|")).join(" // ") : "",
    champs: (rec.final ? t.c : []).slice().sort().join(",")
  };
}
function serverView(rec) {
  const d = T.derive(JSON.parse(JSON.stringify(rec)));
  const nx = d.m.find(x => !(x.s && x.s[0] != null && x.s[1] != null));
  return {
    table: d.table.join(","),
    next: nx ? nx.i : -1,
    legs: d.legs ? d.legs.map(l => [l.home.join("+"), l.hc, l.away.join("+"), l.ac].join("|")).join(" // ") : "",
    champs: (rec.final ? d.champs : []).slice().sort().join(",")
  };
}

let checks = 0, fails = 0, levels = 0;
function compare(rec, label) {
  const a = appView(rec), s = serverView(rec);
  for (const k of Object.keys(a)) {
    checks++;
    if (a[k] !== s[k]) {
      fails++;
      if (fails <= 8) console.log("MISMATCH", label, k, "\n  app:   ", a[k], "\n  server:", s[k]);
    }
  }
}

for (let run = 0; run < 120; run++) {
  const size = run % 3 === 2 ? 5 : 6;
  const slots = shuffle([0, 1, 2, 3, 4, 5]).slice(0, size);
  const clubs = shuffle(RING.slice()).slice(0, size);
  const n = T.TPL[String(size)].length;
  const rec = { i: 1000 + run, s: 1, n: run + 1, tpl: String(size), slots, clubs,
                scores: Array.from({ length: n }, () => [null, null]), champs: [] };
  compare(rec, "run " + run + " start");
  /* results arrive in a random order, as they do on a real evening */
  for (const k of shuffle([...Array(n).keys()])) {
    rec.scores[k] = [goals(), goals()];
    compare(rec, "run " + run + " after match " + (k + 1));
  }
  /* the final: leg one, leg two, sometimes level and settled by golden goal */
  rec.final = [[null, null], [null, null]];
  rec.final[0] = [goals(), goals()];
  compare(rec, "run " + run + " leg 1");
  /* level on aggregate: pair 1-2 scores leg1.away + leg2.home, pair 3-4
     scores leg1.home + leg2.away, so repeating leg one's score draws it */
  const level = rnd() < 0.3;
  rec.final[1] = level ? [rec.final[0][0], rec.final[0][1]] : [goals(), goals()];
  compare(rec, "run " + run + " leg 2");
  if (level) {
    levels++;
    if (appView(rec).champs !== "") { fails++; console.log("level aggregate should leave no champion yet", run); }
    const view = appView(rec);
    const tb = view.table.split(",").map(Number);
    rec.champs = rnd() < 0.5 ? [tb[0], tb[1]] : [tb[2], tb[3]];
    rec.gg = true;
    compare(rec, "run " + run + " golden goal");
  }
}

/* and the real tournament as it stands, through the packed storage format */
const real = { i: 1001, s: 1, n: 1, tpl: "6", slots: [1, 3, 0, 5, 4, 2],
  clubs: ["באיירן", "פסז", "ליברפול", "סיטי", "ריאל", "ברצלונה"],
  scores: [{ __a: [1, 0] }, { __a: [2, 0] }].concat(Array.from({ length: 10 }, () => ({ __a: [null, null] }))), champs: [] };
compare(T.unpack(real), "packed record");
console.log("next push for the packed record:", T.nextEventText(T.unpack(real)));

console.log("\n" + checks + " comparisons, " + fails + " mismatches, " + levels + " finals settled by golden goal");
process.exit(fails ? 1 : 0);
