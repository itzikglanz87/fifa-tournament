/* ============================================================================
   Service worker — so the app opens on the pitch with no signal.

   The whole app is one HTML file, so "offline" mostly means: have that file.
   Navigations go to the network first and fall back to the cached copy, which
   means a published update lands on the next load rather than after a manual
   clear. Everything else same-origin is served from cache and refreshed in the
   background. Firestore and the fonts are left alone — Firestore has its own
   offline queue, and the CSS names system fonts as a fallback.
   ========================================================================= */
const VERSION = "fifa-1dbe20b3b4";
const SHELL = [
  "./",
  "./index.html",
  "./manifest.webmanifest",
  "./db.js",
  "./firebase-config.js",
  "./icons/icon-192.png",
  "./icons/icon-512.png",
  "./icons/icon-maskable-512.png"
];

self.addEventListener("install", e => {
  e.waitUntil((async () => {
    const c = await caches.open(VERSION);
    /* one miss must not fail the whole install */
    await Promise.all(SHELL.map(u => c.add(u).catch(() => {})));
    self.skipWaiting();
  })());
});

self.addEventListener("activate", e => {
  e.waitUntil((async () => {
    const keys = await caches.keys();
    await Promise.all(keys.filter(k => k !== VERSION).map(k => caches.delete(k)));
    await self.clients.claim();
  })());
});

self.addEventListener("message", e => {
  if (e.data === "skipWaiting") self.skipWaiting();
});

self.addEventListener("fetch", e => {
  const req = e.request;
  if (req.method !== "GET") return;

  const url = new URL(req.url);
  if (url.origin !== self.location.origin) return;   // fonts, Firestore: not ours

  /* the page itself: newest if we can reach it, cached if we cannot */
  if (req.mode === "navigate") {
    e.respondWith((async () => {
      try {
        const fresh = await fetch(req);
        const c = await caches.open(VERSION);
        c.put("./index.html", fresh.clone());
        return fresh;
      } catch (err) {
        const c = await caches.open(VERSION);
        return (await c.match("./index.html")) || (await c.match("./")) ||
               new Response("אין חיבור והעותק המקומי חסר.", {
                 status: 503, headers: { "Content-Type": "text/plain; charset=utf-8" } });
      }
    })());
    return;
  }

  /* assets: instant from cache, quietly refreshed for next time */
  e.respondWith((async () => {
    const c = await caches.open(VERSION);
    const hit = await c.match(req);
    const net = fetch(req).then(res => {
      if (res && res.status === 200 && res.type === "basic") c.put(req, res.clone());
      return res;
    }).catch(() => null);
    return hit || (await net) || new Response("", { status: 504 });
  })());
});
