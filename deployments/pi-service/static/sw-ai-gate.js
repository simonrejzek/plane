/* Cosmic AI gate SW — serve patched commercial SPA modules, bypass CF stale HIT */
const PATCHED = {
  "/assets/detail-DFXDSk4X.js": "/cosmic-pilot/static/patched-spa/detail-DFXDSk4X.js",
  "/assets/layout-CR1P7wEo.js": "/cosmic-pilot/static/patched-spa/layout-CR1P7wEo.js",
  "/assets/store-context-BZelk5Qy.js": "/cosmic-pilot/static/patched-spa/store-context-BZelk5Qy.js",
  "/assets/use-ai-flag-CyOtmqWk.js": "/cosmic-pilot/static/patched-spa/use-ai-flag-CyOtmqWk.js",
  "/assets/entry.client-DHb__A1L.js": "/cosmic-pilot/static/patched-spa/entry.client-DHb__A1L.js",
  "/assets/toast-etX1DRQn.js": "/cosmic-pilot/static/patched-spa/toast-etX1DRQn.js",
};

self.addEventListener("install", function (event) {
  self.skipWaiting();
});

self.addEventListener("activate", function (event) {
  event.waitUntil(self.clients.claim());
});

self.addEventListener("fetch", function (event) {
  try {
    var url = new URL(event.request.url);
    var mapped = PATCHED[url.pathname];
    if (!mapped) return;
    event.respondWith(
      fetch(mapped, { cache: "no-store", credentials: "same-origin" }).then(function (res) {
        if (!res.ok) return fetch(event.request);
        return res;
      }).catch(function () {
        return fetch(event.request);
      })
    );
  } catch (_) {}
});
