/* mygov service worker — app shell precache + offline API fallback.
 *
 * Caching strategy, and why it is not textbook stale-while-revalidate:
 *   api.data.gov.my enforces 4 requests per minute per API family. A true SWR
 *   policy fires a background revalidation on every cache hit, which would
 *   silently double request volume and push the app into HTTP 429. So API
 *   responses use cache-fallback: the network result is cached on success, and
 *   the cache is served only when the network fails (offline / rate limited).
 *   Freshness is driven by the app's own 15-minute TTL in index.html, which is
 *   the "revalidate" half of SWR moved into a rate-limit-aware layer.
 */
const VERSION    = "mygov-v4";
const SHELL      = `${VERSION}-shell`;
const API_CACHE  = `${VERSION}-api`;
const KEEP       = new Set([SHELL, API_CACHE]);

const SHELL_ASSETS = [
  "/",
  "/index.html",
  "/manifest.webmanifest",
  "/icons/icon-192.png",
  "/icons/icon-512.png",
  "/icons/apple-touch-icon.png",
  "/vendor/chart.umd.min.js",
  "/vendor/leaflet.min.css",
  "/vendor/leaflet.min.js",
];

self.addEventListener("install", event => {
  event.waitUntil((async () => {
    const cache = await caches.open(SHELL);
    // addAll is atomic — one bad URL fails the whole install, so add
    // individually and tolerate a CDN hiccup.
    await Promise.all(SHELL_ASSETS.map(async url => {
      try { await cache.add(new Request(url, { cache: "reload" })); }
      catch (e) { /* non-fatal: fetched from network on first use */ }
    }));
    await self.skipWaiting();
  })());
});

self.addEventListener("activate", event => {
  event.waitUntil((async () => {
    const names = await caches.keys();
    await Promise.all(names.filter(n => !KEEP.has(n)).map(n => caches.delete(n)));
    await self.clients.claim();
  })());
});

/* Data requests: network first, last-good copy as the offline fallback.
 * raw.githubusercontent.com is included because that is where MoH publishes the
 * KKMNOW health datasets — without it those Parquet files would fall through to
 * the cache-first branch below, which never revalidates, and a daily-updated
 * dataset would be frozen at whatever copy arrived first. */
const isApi = url =>
  url.hostname === "api.data.gov.my" ||
  url.hostname === "raw.githubusercontent.com" ||
  url.pathname.startsWith("/api/");

self.addEventListener("fetch", event => {
  const { request } = event;
  if (request.method !== "GET") return;

  let url;
  try { url = new URL(request.url); } catch { return; }
  if (!/^https?:$/.test(url.protocol)) return;

  // Navigations: network first so a deploy is picked up, cache as fallback.
  if (request.mode === "navigate") {
    event.respondWith((async () => {
      try {
        const fresh = await fetch(request);
        const cache = await caches.open(SHELL);
        cache.put("/index.html", fresh.clone());
        return fresh;
      } catch {
        return (await caches.match("/index.html")) ||
               (await caches.match("/")) ||
               new Response("Offline", { status: 503, headers: { "content-type": "text/plain" } });
      }
    })());
    return;
  }

  // API + reverse-geocode proxy: network, falling back to the last good copy.
  if (isApi(url)) {
    event.respondWith((async () => {
      const cache = await caches.open(API_CACHE);
      try {
        const fresh = await fetch(request);
        // Only cache successes, and never buffer the large GTFS ZIPs (either
        // upstream or via our proxy) — an 8 MB archive per agency would blow
        // through the Cache Storage quota for data the page immediately
        // reduces to a small summary anyway.
        const isZip = url.pathname.startsWith("/gtfs-static") ||
                      url.pathname.startsWith("/api/gtfs");
        if (fresh.ok && !isZip) cache.put(request, fresh.clone());
        return fresh;
      } catch (err) {
        const hit = await cache.match(request);
        if (hit) {
          // Tag it so the page can show an "offline — showing cached" state.
          const headers = new Headers(hit.headers);
          headers.set("x-mygov-cache", "offline");
          return new Response(await hit.blob(), { status: hit.status, headers });
        }
        // No cached copy: let the failure reach the page as a real network
        // error. Synthesising a 503 here would make the app report
        // "the API returned HTTP 503" when the truth is "you are offline".
        throw err;
      }
    })());
    return;
  }

  // Everything else (icons, CDN script): cache first.
  event.respondWith((async () => {
    const hit = await caches.match(request);
    if (hit) return hit;
    try {
      const fresh = await fetch(request);
      if (fresh.ok && url.origin === self.location.origin) {
        const cache = await caches.open(SHELL);
        cache.put(request, fresh.clone());
      }
      return fresh;
    } catch {
      return new Response("", { status: 503 });
    }
  })());
});

self.addEventListener("message", e => {
  if (e.data === "skip-waiting") self.skipWaiting();
});
