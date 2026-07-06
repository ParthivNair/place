/* Place service worker — minimal, honest PWA.
   Shell + manifest + icons cached on install; network-first with cache
   fallback for navigations, the feed, and Next's static chunks (an
   offline navigation replays the cached HTML AND the hashed JS/CSS it
   references, so the last-cached feed actually hydrates, stamped
   "as of <time>" by the UI). Network-first — never cache-first — so a
   dev server's un-hashed chunks are never served stale while online.
   Push → notification → open URL. */

const CACHE = "place-shell-v2";

const PRECACHE = [
  "/",
  "/manifest.webmanifest",
  "/icon.svg",
  "/icon-192.png",
  "/icon-512.png",
];

self.addEventListener("install", (event) => {
  event.waitUntil(caches.open(CACHE).then((cache) => cache.addAll(PRECACHE)));
  self.skipWaiting();
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches
      .keys()
      .then((keys) =>
        Promise.all(keys.filter((key) => key !== CACHE).map((key) => caches.delete(key)))
      )
      .then(() => self.clients.claim())
  );
});

async function networkFirst(request, fallbackUrl) {
  const cache = await caches.open(CACHE);
  try {
    const response = await fetch(request);
    if (response.ok) cache.put(request, response.clone());
    return response;
  } catch (err) {
    const hit = await cache.match(request);
    if (hit) return hit;
    if (fallbackUrl) {
      const shell = await cache.match(fallbackUrl);
      if (shell) return shell;
    }
    throw err;
  }
}

self.addEventListener("fetch", (event) => {
  const { request } = event;
  if (request.method !== "GET") return;
  if (request.mode === "navigate") {
    event.respondWith(networkFirst(request, "/"));
    return;
  }
  const { pathname } = new URL(request.url);
  // Next's build assets — cached as they're fetched so the offline shell
  // has the scripts/styles its cached HTML asks for.
  if (pathname.startsWith("/_next/static/")) {
    event.respondWith(networkFirst(request));
    return;
  }
  // The feed API (real mode; mock mode bundles fixtures and never hits
  // this) — pathname-only match works same-origin; a cross-origin API
  // host passes through untouched (flagged: untested plumbing until the
  // real API fronts the PWA).
  if (pathname === "/feed") {
    event.respondWith(networkFirst(request));
  }
});

self.addEventListener("push", (event) => {
  if (!event.data) return;
  const payload = event.data.json();
  event.waitUntil(
    self.registration.showNotification(payload.title, {
      body: payload.body,
      data: { url: payload.url },
    })
  );
});

self.addEventListener("notificationclick", (event) => {
  event.notification.close();
  const url = (event.notification.data && event.notification.data.url) || "/";
  event.waitUntil(self.clients.openWindow(url));
});
