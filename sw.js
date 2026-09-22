/* ============================================================================
   Service worker — so the app opens on the pitch with no signal.

   The whole app is one HTML file, so "offline" mostly means: have that file.
   Navigations go to the network first and fall back to the cached copy, which
   means a published update lands on the next load rather than after a manual
   clear. Everything else same-origin is served from cache and refreshed in the
   background. Firestore and the fonts are left alone — Firestore has its own
   offline queue, and the CSS names system fonts as a fallback.
   ========================================================================= */
const VERSION = "fifa-0549d2a8dc";
const SHELL = [
  "./",
  "./index.html",
  "./manifest.webmanifest",
  "./db.js",
  "./firebase-config.js",
  "./icons/icon-192.png",
  "./icons/icon-512.png",
  "./icons/icon-maskable-512.png",
  "./icons/badge-96.png"
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

/* ---------------------------------------------------------------------------
   Push. The server sends data-only messages through Firebase Cloud Messaging,
   and this worker draws every one of them — so a notification looks the same
   whether the app is open, in the background or closed. Chrome requires a
   visible notification for every push, and this always shows one.
   ------------------------------------------------------------------------- */
self.addEventListener("push", e => {
  let d = {};
  try {
    const j = e.data ? e.data.json() : {};
    d = j.data || j.notification || j;
  } catch (err) {
    d = { body: e.data ? e.data.text() : "" };
  }
  const title = d.title || "טורניר פיפא";
  e.waitUntil(self.registration.showNotification(title, {
    body: d.body || "",
    icon: "icons/icon-192.png",
    badge: "icons/badge-96.png",          // the status bar wants a white silhouette
    dir: "rtl",
    lang: "he",
    tag: d.tag || undefined,              // the poll's reminder replaces the poll's push
    renotify: !!d.tag,
    data: { url: d.url || "./" }
  }));
});

/* a tap on the notification brings the app forward, or opens it. A push
   that carries a newsroom card (#story=<id>) tells an open app to show it;
   a closed app is opened on it. */
self.addEventListener("notificationclick", e => {
  e.notification.close();
  const url = (e.notification.data && e.notification.data.url) || "./";
  const m = /#story=([\w-]+)/.exec(url), poll = /#poll$/.test(url);
  e.waitUntil((async () => {
    const wins = await self.clients.matchAll({ type: "window", includeUncontrolled: true });
    for (const w of wins) {
      if ("focus" in w) {
        if (m) w.postMessage({ story: m[1] });
        if (poll) w.postMessage({ poll: 1 });
        return w.focus();
      }
    }
    if (self.clients.openWindow) return self.clients.openWindow(url);
  })());
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
