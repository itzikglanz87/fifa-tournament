/* ============================================================================
   Firestore, wearing the shape the app already expects.

   The app talks to its store through exactly four calls:

       db.doc(path).get()      -> { exists, data() }
       db.doc(path).set(obj)
       db.doc(path).delete()
       db.collection(path).get() -> { docs: [{ data() }] }

   That is the same surface the artifact runtime hands it, so nothing above
   this file changes between the two builds. If Firebase is not configured,
   or cannot be reached, open() resolves to null and the app falls back to
   its own per-device storage — which it already knows how to do.

   Loaded as a CLASSIC script so window.APP_DB exists before the app script
   runs; the Firebase SDK itself is pulled in with a dynamic import inside
   open(), which is async anyway.
   ========================================================================= */
(function () {
  "use strict";

  var SDK = "https://www.gstatic.com/firebasejs/10.12.5/";
  var started = null;

  function configured() {
    var c = window.FIREBASE_CONFIG;
    return !!(c && c.projectId && c.apiKey &&
              String(c.apiKey).indexOf("PASTE") !== 0 &&
              String(c.projectId).indexOf("PASTE") !== 0);
  }

  /* "tournaments/t52" -> ["tournaments", "t52"] */
  function parts(path) {
    return String(path).split("/").filter(Boolean);
  }

  /* Firestore refuses an array directly inside an array, and every
     tournament is built of them: scores [[h,a], ...], final [[h,a],[h,a]].
     Each inner array is wrapped as {__a: [...]} on the way in (an array may
     hold a map, and a map may hold an array) and unwrapped on the way out,
     so the app never sees the difference. */
  function pack(v) {
    if (Array.isArray(v)) return v.map(function (e) { return Array.isArray(e) ? { __a: pack(e) } : pack(e); });
    if (v && typeof v === "object") {
      var o = {};
      Object.keys(v).forEach(function (k) { o[k] = pack(v[k]); });
      return o;
    }
    return v;
  }
  function unpack(v) {
    if (Array.isArray(v)) return v.map(unpack);
    if (v && typeof v === "object") {
      var keys = Object.keys(v);
      if (keys.length === 1 && keys[0] === "__a" && Array.isArray(v.__a)) return unpack(v.__a);
      var o = {};
      keys.forEach(function (k) { o[k] = unpack(v[k]); });
      return o;
    }
    return v;
  }
  window.APP_DB_CODEC = { pack: pack, unpack: unpack };   // exposed for tests

  async function build() {
    var appMod = await import(SDK + "firebase-app.js");
    var authMod = await import(SDK + "firebase-auth.js");
    var fsMod = await import(SDK + "firebase-firestore.js");

    var app = appMod.initializeApp(window.FIREBASE_CONFIG);

    /* Anonymous sign-in: the rules require an authenticated caller, which
       keeps drive-by writes out. It is not identity — see README. */
    var auth = authMod.getAuth(app);
    await new Promise(function (resolve) {
      var done = false;
      var stop = authMod.onAuthStateChanged(auth, function (u) {
        if (u && !done) { done = true; stop(); resolve(u); }
      });
      authMod.signInAnonymously(auth).catch(function () {
        if (!done) { done = true; resolve(null); }
      });
      setTimeout(function () { if (!done) { done = true; resolve(null); } }, 8000);
    });

    var fs = fsMod.getFirestore(app);
    /* Offline cache: reads work on the train, writes queue and flush later. */
    try {
      await fsMod.enableIndexedDbPersistence(fs);
    } catch (e) {
      /* another tab already holds it, or the browser refuses — not fatal */
    }

    return {
      doc: function (path) {
        var ref = fsMod.doc.apply(null, [fs].concat(parts(path)));
        return {
          get: async function () {
            var snap = await fsMod.getDoc(ref);
            return { exists: snap.exists(), data: function () { return unpack(snap.data()); } };
          },
          set: function (obj) { return fsMod.setDoc(ref, pack(obj)); },
          delete: function () { return fsMod.deleteDoc(ref); }
        };
      },
      collection: function (path) {
        var ref = fsMod.collection.apply(null, [fs].concat(parts(path)));
        return {
          get: async function () {
            var snap = await fsMod.getDocs(ref);
            var docs = [];
            snap.forEach(function (d) {
              docs.push({ id: d.id, data: function () { return unpack(d.data()); } });
            });
            return { docs: docs };
          }
        };
      }
    };
  }

  window.APP_DB = {
    configured: configured,
    open: function () {
      if (!configured()) return Promise.resolve(null);
      if (!started) {
        started = build().catch(function (err) {
          window.APP_DB_ERROR = (err && (err.code || err.message)) || String(err);
          return null;
        });
      }
      return started;
    }
  };
})();
