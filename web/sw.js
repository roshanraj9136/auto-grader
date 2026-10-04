// Service worker: makes AutoGrader+ installable and keeps the app shell available offline.
// Strategy: network-first for everything (fresh deploys win), cached app shell as the offline fallback.
// API calls, SSE streams and reports are never cached.
const CACHE = "autograder-shell-v3";
const SHELL = [
  "/", "/styles.css", "/theme.js", "/app.js", "/js/core.js", "/js/pages/landing.js", "/js/pages/student.js", "/js/pages/grader.js",
  "/js/pages/instructor.js", "/js/pages/labs.js", "/js/pages/system.js", "/manifest.webmanifest", "/icons/icon.svg",
  "/icons/icon-192.png",
];

self.addEventListener("install", (e) => {
  e.waitUntil(caches.open(CACHE).then((c) => c.addAll(SHELL)).then(() => self.skipWaiting()));
});

self.addEventListener("activate", (e) => {
  e.waitUntil(caches.keys().then((keys) => Promise.all(keys.filter((k) => k !== CACHE).map((k) => caches.delete(k))))
    .then(() => self.clients.claim()));
});

self.addEventListener("fetch", (e) => {
  const url = new URL(e.request.url);
  if (e.request.method !== "GET" || url.origin !== location.origin) return;
  if (url.pathname.startsWith("/api/") || url.pathname.startsWith("/lb/") || url.pathname === "/sandbox.html") return;
  e.respondWith(
    fetch(e.request)
      .then((res) => {
        if (res.ok && SHELL.includes(url.pathname)) {
          const copy = res.clone();
          caches.open(CACHE).then((c) => c.put(e.request, copy));
        }
        return res;
      })
      .catch(async () => (await caches.match(e.request)) || (e.request.mode === "navigate" ? caches.match("/") : Response.error())),
  );
});
