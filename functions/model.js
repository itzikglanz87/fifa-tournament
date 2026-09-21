/* ============================================================================
   The app's odds model, running on the server.

   app-rules.js is cut straight out of the built app by src/build.py, so the
   percentages in a "peak moment" push are the ones the app itself would show.
   It is plain browser code that expects its data as globals, so it runs in a
   fresh vm sandbox per call — cheap next to a network round trip, and no
   state leaks from one tournament's push into the next.
   ========================================================================= */
"use strict";
const fs = require("fs"), path = require("path"), vm = require("vm");

const CODE = fs.readFileSync(path.join(__dirname, "app-rules.js"), "utf8");
const SEED = JSON.parse(fs.readFileSync(path.join(__dirname, "seed.json"), "utf8"));
const script = new vm.Script(
  "const SEED = __SEED; const PHOTOS = {};\n" + CODE + "\n" +
  "this.kit = { LIVE, hydrate, decorate, rebuild, simulate, achievements, ACH, P, CLUBS," +
  " setSeasons: v => { SEASONS = v; }, model: () => MODEL };");

/* recs: every tournament record in the store (unpacked), live and finished */
function makeKit(recs, seasons) {
  const ctx = { __SEED: SEED, console, document: undefined, window: {}, localStorage: undefined };
  vm.createContext(ctx);
  script.runInContext(ctx);
  const K = ctx.kit;
  if (Array.isArray(seasons) && seasons.length) K.setSeasons(seasons.map(s => ({ id: s.id, name: s.name })));
  (recs || []).forEach(r => { if (r && r.i) K.LIVE[r.i] = K.hydrate(JSON.parse(JSON.stringify(r))); });
  K.rebuild();                        // archive + store -> the same MODEL the app builds
  return K;
}

module.exports = { makeKit };
