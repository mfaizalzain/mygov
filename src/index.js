/**
 * mygov Worker.
 *
 * Serves the static site from public/ (via the ASSETS binding) and adds one
 * tiny API route:
 *
 *   GET /api/reverse?lat=..&lon=..  →  reverse geocode via Nominatim
 *
 * Why this route exists rather than calling Nominatim from the browser:
 *   1. nominatim.openstreetmap.org sends no `access-control-allow-origin`
 *      header, so a direct browser fetch is blocked by CORS.
 *   2. Their usage policy requires a descriptive User-Agent identifying the
 *      app. Browsers forbid scripts from setting User-Agent, so only a
 *      server-side call can comply.
 *   3. Proxying lets us cache at the edge, which keeps us comfortably inside
 *      Nominatim's 1-request-per-second guidance no matter how many visitors
 *      the site has.
 */

const NOMINATIM = "https://nominatim.openstreetmap.org/reverse";
const UA = "mygov-dashboard/1.0 (+https://mygov.faizalmzain.com)";
const CACHE_TTL = 86400;   // a coordinate's town doesn't change; cache a day

const json = (body, status = 200, extra = {}) =>
  new Response(JSON.stringify(body), {
    status,
    headers: {
      "content-type": "application/json; charset=utf-8",
      "access-control-allow-origin": "*",
      "cache-control": `public, max-age=${CACHE_TTL}`,
      ...extra,
    },
  });

export default {
  async fetch(request, env, ctx) {
    const url = new URL(request.url);

    if (url.pathname === "/api/reverse") {
      if (request.method !== "GET")
        return json({ error: "method_not_allowed" }, 405);

      const lat = Number(url.searchParams.get("lat"));
      const lon = Number(url.searchParams.get("lon"));
      if (!Number.isFinite(lat) || !Number.isFinite(lon) ||
          lat < -90 || lat > 90 || lon < -180 || lon > 180)
        return json({ error: "bad_coordinates" }, 400);

      // Round to ~1 km so nearby visitors share one cache entry and we send
      // far fewer requests upstream. Also avoids storing precise locations.
      const rlat = lat.toFixed(2), rlon = lon.toFixed(2);
      const cacheKey = new Request(
        `${url.origin}/api/reverse?lat=${rlat}&lon=${rlon}`, { method: "GET" });
      const cache = caches.default;

      const hit = await cache.match(cacheKey);
      if (hit) return hit;

      const upstream = `${NOMINATIM}?format=json&zoom=10&addressdetails=1&lat=${rlat}&lon=${rlon}`;
      let res;
      try {
        res = await fetch(upstream, {
          headers: { "user-agent": UA, accept: "application/json" },
          cf: { cacheTtl: CACHE_TTL, cacheEverything: true },
        });
      } catch {
        return json({ error: "upstream_unreachable" }, 502);
      }
      if (!res.ok) return json({ error: "upstream_error", status: res.status }, 502);

      let data;
      try { data = await res.json(); }
      catch { return json({ error: "bad_upstream_payload" }, 502); }

      // Return only what the client actually matches on — no need to hand back
      // the full Nominatim record.
      const a = data.address || {};
      const out = {
        address: {
          city: a.city, town: a.town, village: a.village, suburb: a.suburb,
          county: a.county, state_district: a.state_district, state: a.state,
          country_code: a.country_code,
        },
        display_name: data.display_name,
      };
      const response = json(out);
      ctx.waitUntil(cache.put(cacheKey, response.clone()));
      return response;
    }

    // Everything else is a static asset.
    return env.ASSETS.fetch(request);
  },
};
