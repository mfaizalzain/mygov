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
      // Only same-origin callers. This route exists for our own page; without
      // this it is a free, cached geocoding endpoint for anyone who finds it.
      const origin = request.headers.get("origin");
      if (origin && new URL(request.url).origin !== origin)
        return json({ error: "forbidden" }, 403);

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

    /* GTFS static ZIP proxy.
     *
     * /gtfs-static/* on the upstream API answers 302 to an S3 bucket. A
     * browser then has to pass CORS on the *redirect target*, which is
     * fragile — any network layer that intercepts that hop surfaces it as an
     * opaque "CORS error" with no way for the page to distinguish it from
     * being offline. Fetching it server-side removes the cross-origin hop
     * entirely, and edge-caching means the government API sees a handful of
     * requests per day instead of one 8 MB download per visitor. */
    if (url.pathname === "/api/gtfs") {
      const origin = request.headers.get("origin");
      if (origin && url.origin !== origin) return json({ error: "forbidden" }, 403);

      const agency = url.searchParams.get("agency") || "";
      const category = url.searchParams.get("category") || "";
      // Strict allowlist — never interpolate user input into the upstream URL.
      if (!/^[a-z0-9-]{1,32}$/.test(agency) || (category && !/^[a-z0-9-]{1,32}$/.test(category)))
        return json({ error: "bad_agency" }, 400);

      const upstream = new URL(`https://api.data.gov.my/gtfs-static/${agency}/`);
      if (category) upstream.searchParams.set("category", category);

      const cacheKey = new Request(`${url.origin}/api/gtfs?agency=${agency}&category=${category}`);
      const cache = caches.default;
      const hit = await cache.match(cacheKey);
      if (hit) return hit;

      let res;
      try { res = await fetch(upstream, { redirect: "follow" }); }
      catch { return json({ error: "upstream_unreachable" }, 502); }
      if (!res.ok)
        return json({ error: "upstream_error", status: res.status }, res.status === 429 ? 429 : 502);

      const out = new Response(res.body, {
        status: 200,
        headers: {
          "content-type": "application/zip",
          "access-control-allow-origin": url.origin,
          // Schedules are republished daily at most.
          "cache-control": "public, max-age=21600",
        },
      });
      ctx.waitUntil(cache.put(cacheKey, out.clone()));
      return out;
    }

    /* Malaysia Airports FIDS (flight information display) proxy.
     *
     * The official live arrivals/departures board on malaysiaairports.com.my
     * calls api.myairports.com.my with a public x-api-key embedded in its JS
     * bundle. The API sends no `access-control-allow-origin`, so browsers
     * cannot call it directly — same story as Nominatim above. Proxying here
     * keeps the key server-side (it is public, but living in one place makes
     * rotation trivial) and edge-caches the board so upstream sees one
     * request per TTL regardless of visitors. Boards refresh roughly every
     * minute on the site; 90 s is a fair middle ground. */
    if (url.pathname === "/api/fids") {
      const origin = request.headers.get("origin");
      if (origin && url.origin !== origin) return json({ error: "forbidden" }, 403);

      const code = url.searchParams.get("code") || "A";
      const terminal = url.searchParams.get("terminal") || "KLIA";
      const dayKey = url.searchParams.get("dayKey") || "0";
      // Strict allowlist — never interpolate user input into the upstream URL.
      if (!/^[AD]$/.test(code)) return json({ error: "bad_code" }, 400);
      if (!/^[a-zA-Z0-9-]{1,16}$/.test(terminal)) return json({ error: "bad_terminal" }, 400);
      if (!/^[0-9]$/.test(dayKey)) return json({ error: "bad_dayKey" }, 400);

      const upstream = new URL(
        "https://api.myairports.com.my/passenger-fids/api/flights/search-flights");
      upstream.searchParams.set("code", code);
      upstream.searchParams.set("key", "all");
      upstream.searchParams.set("terminal", terminal);
      upstream.searchParams.set("dayKey", dayKey);
      upstream.searchParams.set("live", "true");
      upstream.searchParams.set("skip", "0");
      upstream.searchParams.set("take", "200");

      const cacheKey = new Request(
        `${url.origin}/api/fids?code=${code}&terminal=${terminal}&dayKey=${dayKey}`);
      const cache = caches.default;
      const hit = await cache.match(cacheKey);
      if (hit) return hit;

      let res;
      try {
        res = await fetch(upstream, {
          headers: {
            "x-api-key": env.FIDS_API_KEY,
            accept: "application/json",
          },
          cf: { cacheTtl: 90, cacheEverything: true },
        });
      } catch {
        return json({ error: "upstream_unreachable" }, 502);
      }
      if (!res.ok)
        return json({ error: "upstream_error", status: res.status }, res.status === 429 ? 429 : 502);

      let data;
      try { data = await res.json(); }
      catch { return json({ error: "bad_upstream_payload" }, 502); }

      // Slim the payload: the dashboard renders a board, not codeshares and
      // baggage belt metadata. Keeping only the columns the UI needs trims a
      // ~1.5 MB response to a few KB and makes the client simpler.
      const slim = (data.flightStatuses || []).map(f => ({
        flightNumber: f.flightNumber,
        airline: (f.airline && f.airline.name) || f.name || "",
        aircraftOperator: f.aircraftOperator,
        origin: f.origin && f.origin.city,
        destination: f.destination && f.destination.city,
        scheduled: f.scheduledTime || f.flightTime,
        status: f.status || "",
        statusCode: f.statusCode || "",
        gate: f.gate && f.gate.name,
        belt: f.belt && f.belt.name,
        terminal: f.terminal,
        codeshares: (f.codeShareFlights || []).map(c => c.flightNumber),
      }));
      const out = json({
        count: data.count,
        flights: slim,
      }, 200, { "cache-control": "public, max-age=90" });
      ctx.waitUntil(cache.put(cacheKey, out.clone()));
      return out;
    }

    // Everything else is a static asset. Security headers for those come from
    // public/_headers — the asset router serves them without running this
    // Worker, so setting headers here would have no effect.
    return env.ASSETS.fetch(request);
  },
};
