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
      "x-content-type-options": "nosniff",
      "cache-control": `public, max-age=${CACHE_TTL}`,
      ...extra,
    },
  });

/* ── Upstream parameter allowlists ────────────────────────────────────
 *
 * These used to be shape checks (`/^[a-z0-9-]{1,32}$/`), which accept ~10^48
 * values where the app only ever sends two or three. That mattered more than
 * it looks: every distinct value is a distinct edge-cache key, so a loop over
 * junk values never hits cache and turns each proxy route into an
 * amplifier - one cheap inbound request became a full upstream fetch, and for
 * /api/rapid a four-request socket.io handshake with a 1.5 s sleep against
 * Prasarana's kiosk. Enumerating the real values caps the cache-key space, so
 * upstream load is bounded by the cache TTL no matter what arrives.
 *
 * Keep these in sync with the client: GTFS_PAIRS with the feed list in
 * app.js, FIDS_TERMINALS with F_AIRPORTS. */
const GTFS_PAIRS = new Set([
  "ktmb|",
  "prasarana|rapid-bus-kl",
  "prasarana|rapid-rail-kl",
  /* Names only, for the live map. The kiosk feed reports ~100 T-prefixed MRT
     feeder routes that rapid-bus-kl does not carry, and Penang's routes are
     in neither; without these both show as bare codes. There is no
     rapid-bus-kuantan upstream (404), which is why RKN has no entry. */
  "prasarana|rapid-bus-mrtfeeder",
  "prasarana|rapid-bus-penang",
]);
const FIDS_TERMINALS = new Set([
  "KLIA", "klia2", "SZB", "PEN", "BKI", "KCH", "LGK",
  "KBR", "TWU", "AOR", "TGG", "LBU", "IPH",
]);
const RAPID_PROVIDERS = new Set(["RKL", "RPG", "RKN"]);
/* Place names only: letters (incl. accented), digits, space and . ' ( ) -
 * This is the one route whose value space cannot be enumerated - the MET
 * location list lives in the upstream payload, not here - so it leans on the
 * rate limiter below instead. */
const GEOCODE_Q = /^[\p{L}\p{N} .'()-]{2,60}$/u;

/* Same-origin + rate-limit gate for the proxy routes.
 *
 * The previous check was `if (origin && url.origin !== origin) 403`, which
 * skipped itself whenever the Origin header was absent - that is, for every
 * non-browser client, which is exactly who abuse comes from. Sec-Fetch-Site
 * closes that hole: browsers always send it on fetch(), and only our own page
 * sends `same-origin` (a direct navigation sends `none`). It is still only
 * checked when present, so a header-stripping extension or an ancient browser
 * degrades to the rate limiter rather than to a 403.
 *
 * The limiter is keyed on IP + path. It is per-colo and best-effort by
 * design - it is an abuse cap, not a quota - and the binding is optional so
 * `wrangler dev` and the staging deploy still work without it. */
async function guard(request, url, env) {
  const origin = request.headers.get("origin");
  if (origin && url.origin !== origin) return json({ error: "forbidden" }, 403);
  const site = request.headers.get("sec-fetch-site");
  if (site && site !== "same-origin") return json({ error: "forbidden" }, 403);
  if (env.API_RATE_LIMIT) {
    const ip = request.headers.get("cf-connecting-ip") || "anon";
    const { success } = await env.API_RATE_LIMIT.limit({ key: `${ip}|${url.pathname}` });
    if (!success)
      return json({ error: "rate_limited" }, 429, { "retry-after": "60" });
  }
  return null;
}

export default {
  async fetch(request, env, ctx) {
    const url = new URL(request.url);

    // MCP, SSE, and OpenAPI proxy to the dedicated MCP worker (mcp.malaysia-at-a-glance.com)
    if (
      url.pathname === "/mcp" ||
      url.pathname === "/sse" ||
      url.pathname === "/openapi.json" ||
      url.pathname === "/openapi.yaml" ||
      url.pathname.startsWith("/api/mygov_") ||
      url.pathname.startsWith("/tools/mygov_") ||
      (request.method === "POST" && url.pathname === "/") ||
      (request.method === "GET" && (request.headers.get("accept") || "").includes("text/event-stream"))
    ) {
      const mcpUrl = new URL(request.url);
      mcpUrl.hostname = "mcp.malaysia-at-a-glance.com";
      return fetch(mcpUrl.toString(), request);
    }

    if (url.pathname === "/api/reverse") {
      if (request.method !== "GET")
        return json({ error: "method_not_allowed" }, 405);


      const lat = Number(url.searchParams.get("lat"));
      const lon = Number(url.searchParams.get("lon"));
      if (!Number.isFinite(lat) || !Number.isFinite(lon) ||
          lat < -90 || lat > 90 || lon < -180 || lon > 180)
        return json({ error: "bad_coordinates" }, 400);

      // Only same-origin callers. This route exists for our own page; without
      // this it is a free, cached geocoding endpoint for anyone who finds it.
      const denied = await guard(request, url, env);
      if (denied) return denied;

      // Round to ~1 km so nearby visitors share one cache entry and we send
      // far fewer requests upstream. Also avoids storing precise locations.
      const rlat = lat.toFixed(2), rlon = lon.toFixed(2);
      const cacheKey = new Request(
        `${url.origin}/api/reverse?lat=${rlat}&lon=${rlon}`, { method: "GET" });
      const cache = caches.default;

      const hit = await cache.match(cacheKey);
      if (hit) return hit;

      const upstream = `${NOMINATIM}?format=json&zoom=13&addressdetails=1&lat=${rlat}&lon=${rlon}`;
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

      // Return only what the client actually matches on - no need to hand back
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

    /* Forward geocoding: town name -> coordinates, used by the weather "Now"
       map to pin the selected location. Same wrapper as /api/reverse -
       Nominatim needs a descriptive User-Agent and a browser cannot set one.
       Restricted to Malaysia (countrycodes=my) so an ambiguous town name can
       never resolve to a same-named city abroad. Rounding is done client-side
       before the map is drawn. */
    if (url.pathname === "/api/geocode") {
      if (request.method !== "GET")
        return json({ error: "method_not_allowed" }, 405);
      const denied = await guard(request, url, env);
      if (denied) return denied;
      /* Normalise before validating AND before keying the cache: "Kuala  Lumpur"
         and "kuala lumpur" are the same lookup, and letting them be two cache
         entries is the cache-busting hole in miniature. */
      const q = (url.searchParams.get("q") || "")
        .trim().replace(/\s+/g, " ").slice(0, 60);
      if (!q || !GEOCODE_Q.test(q)) return json({ error: "bad_query" }, 400);
      const cacheKey = new Request(
        `${url.origin}/api/geocode?q=${encodeURIComponent(q.toLowerCase())}`,
        { method: "GET" });
      const cache = caches.default;
      const hit = await cache.match(cacheKey);
      if (hit) return hit;
      const upstream =
        `https://nominatim.openstreetmap.org/search?format=json&limit=1&countrycodes=my&q=${encodeURIComponent(q)}`;
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
      const top = (Array.isArray(data) ? data : [])[0];
      if (!top) return json({ error: "not_found" }, 404);
      const out = json({ lat: Number(top.lat), lon: Number(top.lon), label: top.display_name });
      ctx.waitUntil(cache.put(cacheKey, out.clone()));
      return out;
    }

    /* GTFS static ZIP proxy.
     *
     * /gtfs-static/* on the upstream API answers 302 to an S3 bucket. A
     * browser then has to pass CORS on the *redirect target*, which is
     * fragile - any network layer that intercepts that hop surfaces it as an
     * opaque "CORS error" with no way for the page to distinguish it from
     * being offline. Fetching it server-side removes the cross-origin hop
     * entirely, and edge-caching means the government API sees a handful of
     * requests per day instead of one 8 MB download per visitor. */
    if (url.pathname === "/api/gtfs") {
      const denied = await guard(request, url, env);
      if (denied) return denied;

      const agency = url.searchParams.get("agency") || "";
      const category = url.searchParams.get("category") || "";
      /* Allowlist the PAIR, not each part: "ktmb|rapid-rail-kl" is not a real
         feed, and each accepted combination is another 8 MB ZIP the edge has
         to fetch and hold. */
      if (!GTFS_PAIRS.has(`${agency}|${category}`))
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

    /* Rapid KL / Penang / Kuantan live bus positions (myrapidbus kiosk feed).
     *
     * The api.data.gov.my GTFS-RT feed for prasarana is frequently empty even
     * mid-service, but the official kiosk (myrapidbus.prasarana.com.my/kiosk)
     * shows 800+ live buses from a socket.io server. socket.io's engine.io
     * POLLING transport is plain HTTP, so a Worker can consume it without a
     * websocket client: GET open -> POST connect -> POST emit -> GET poll,
     * then the 42["onFts-client",...] frame carries base64(gzip(JSON)).
     * Proxying server-side keeps the kiosk's shared sid private-ish and edge
     * caches for ~25 s so every visitor shares one upstream poll. */
    if (url.pathname === "/api/rapid") {
      const denied = await guard(request, url, env);
      if (denied) return denied;

      const provider = (url.searchParams.get("provider") || "RKL").toUpperCase();
      if (!RAPID_PROVIDERS.has(provider))
        return json({ error: "bad_provider" }, 400);
      /* `route` used to be a caller-supplied filter, but the client has always
         asked for the full fleet and filtered chips locally - so it only ever
         widened the cache-key space in front of the most expensive upstream
         call on the site (handshake + 1.5 s sleep per miss). Always request
         every route; three providers means at most three cache keys. */
      const route = "";

      const cacheKey = new Request(`${url.origin}/api/rapid?provider=${provider}`);
      const cache = caches.default;
      const hit = await cache.match(cacheKey);
      if (hit) return hit;

      const KIOSK_SID = "m0ckulfr515l5s79sgd2hhva9iqm3cr2";
      const KIOSK = "https://rapidbus-socketio-avl.prasarana.com.my/socket.io/";
      const base64decode = s => {
        const bin = atob(s);
        const bytes = new Uint8Array(bin.length);
        for (let i = 0; i < bin.length; i++) bytes[i] = bin.charCodeAt(i);
        return bytes;
      };
      let data;
      try {
        const openRes = await fetch(`${KIOSK}?EIO=4&transport=polling&t=${Date.now()}`,
          { headers: { "user-agent": UA } });
        const openText = await openRes.text();
        const m = openText.match(/^0\{"sid":"([^"]+)"/);
        if (!m) throw new Error("handshake");
        const sid = m[1];
        const post = async payload => {
          await fetch(`${KIOSK}?EIO=4&transport=polling&sid=${sid}&t=${Date.now()}`, {
            method: "POST",
            headers: { "content-type": "text/plain;charset=UTF-8", "user-agent": UA },
            body: payload,
          });
        };
        await post(`40{"sid":"${KIOSK_SID}","uid":""}`);
        await post(`42["onFts-reload",{"sid":"${KIOSK_SID}","uid":"",` +
          `"provider":"${provider}","route":"${route}"}]`);
        await new Promise(r => setTimeout(r, 1500));
        const pollRes = await fetch(`${KIOSK}?EIO=4&transport=polling&sid=${sid}&t=${Date.now()}`,
          { headers: { "user-agent": UA } });
        const pollText = await pollRes.text();
        let payload = null;
        for (const frame of pollText.split("\x1e")) {
          const fm = frame.match(/^42\["onFts-client","(.*)"\]$/s);
          if (fm) { payload = fm[1]; break; }
        }
        if (!payload) throw new Error("no frame");
        const ds = new DecompressionStream("gzip");
        const stream = new Blob([base64decode(payload)]).stream().pipeThrough(ds);
        const text = new TextDecoder().decode(await new Response(stream).arrayBuffer());
        data = JSON.parse(text);
      } catch (e) {
        return json({ error: "kiosk_unreachable" }, 502);
      }

      const buses = Array.isArray(data) ? data : [];
      /* Slim to what the dashboard renders; dt_gps is MYT wall-clock (UTC+8,
         no DST), so convert to an epoch timestamp for the client. */
      const slim = buses.map(b => ({
        bus_no: b.bus_no,
        latitude: b.latitude,
        longitude: b.longitude,
        route: b.route,
        speed: b.speed,
        dir: b.dir,
        ts: b.dt_gps ? Math.floor(Date.parse(String(b.dt_gps).replace(" ", "T") + "+08:00") / 1000) : null,
      }));
      const out = json({
        provider, route: route || "all",
        live_buses: buses.length,
        updated: new Date().toISOString(),
        buses: slim,
      }, 200, { "cache-control": "public, max-age=25" });
      ctx.waitUntil(cache.put(cacheKey, out.clone()));
      return out;
    }

    /* JPS flood / water level proxy.
     *
     * publicinfobanjir.water.gov.my serves its live telemetry as static JSON
     * files on the WordPress theme path (the old /waterlevel/ endpoints are
     * gone). The two feeds:
     *   - latestreadingstrendabc.json (~1.3 MB, all 2700+ stations): current
     *     water level (m), status (Danger/Warning/Alert/Normal/Error), trend
     *     (Rising/Steady/Receding), lat/lon, district/state, last reading ts.
     *     Fields are single letters (a..nn) - legacy, no header.
     *   - newrtureadings.json (~100 KB): station metadata + telemetry flags.
     * The browser cannot reasonably ship 1.3 MB per visitor, so this route
     * slims to the at-risk stations only (Danger/Warning/Alert) plus a
     * per-state summary. Edge-caches 5 min - flood telemetry updates every
     * 15 min upstream, so 5 min is a fair sharing window. */
    if (url.pathname === "/api/flood") {
      const denied = await guard(request, url, env);
      if (denied) return denied;

      /* KV-first: the collect_hazards workflow uploads the slim flood result
         under "flood". Serving that skips the 1.3 MB upstream fetch and the
         per-request filter/summary pass; the live fetch below is only the
         fallback. */
      try {
        const kv = await env.MYGOV_DATA.get("flood");
        if (kv != null) {
          const parsed = JSON.parse(kv);
          if (parsed && Array.isArray(parsed.stations)) {
            return json(parsed, 200, { "cache-control": "public, max-age=300" });
          }
        }
      } catch { /* corrupt or missing KV value - fall through to live fetch */ }

      const FEED = "https://publicinfobanjir.water.gov.my/wp-content/themes/enlighten/data/latestreadingstrendabc.json";
      let res;
      try {
        res = await fetch(FEED, { headers: { "user-agent": UA }, cf: { cacheTtl: 300, cacheEverything: true } });
      } catch {
        return json({ error: "upstream_unreachable" }, 502);
      }
      if (!res.ok)
        return json({ error: "upstream_error", status: res.status }, res.status === 429 ? 429 : 502);

      let rows;
      try { rows = await res.json(); }
      catch { return json({ error: "bad_upstream_payload" }, 502); }

      const now = Date.now();
      const parseTs = s => {
        if (!s) return null;
        const m = String(s).match(/^(\d{2})\/(\d{2})\/(\d{4})[ T](\d{2}):(\d{2})/);
        if (!m) return null;
        // JPS timestamps are local (MYT, UTC+8, no DST).
        return Math.floor(Date.parse(`${m[3]}-${m[2]}-${m[1]}T${m[4]}:${m[5]}:00+08:00`) / 1000);
      };
      const num = v => {
        const n = Number(v);
        return Number.isFinite(n) ? n : null;
      };

      const atRisk = [];
      const stateStats = {};
      const WATCH = new Set(["Danger", "Warning", "Alert"]);
      // Only CURRENT risk: the feed carries dead telemetry (last reading
      // months/years old) alongside live stations. A 2025 "Danger" marker is
      // not today's flood risk - it is a broken gauge. Require a reading
      // within 24h so the map shows today's picture only.
      const FRESH_MS = 24 * 3600 * 1000;
      // A receding gauge is past its peak: a Warning/Alert station whose water
      // is going DOWN is not an active warning. Danger always stays - the
      // station is currently flooded regardless of direction (user rule,
      // 2026-08-11).
      const RECEDING = new Set(["Receding", "Falling"]);
      for (const s of Array.isArray(rows) ? rows : []) {
        const status = String(s.n || "");
        if (!WATCH.has(status)) continue;
        const trend = String(s.s || "");
        if (status !== "Danger" && RECEDING.has(trend)) continue;
        const ts = parseTs(s.q) ? parseTs(s.q) * 1000 : null;
        if (!ts || now - ts > FRESH_MS) continue;
        const state = String(s.f || "Unknown");
        stateStats[state] = (stateStats[state] || 0) + 1;
        atRisk.push({
          id: String(s.a || ""),
          name: String(s.b || ""),
          lat: num(s.c), lon: num(s.d),
          district: String(s.e || ""), state,
          river: String(s.g || ""), basin: String(s.h || ""),
          type: String(s.i || ""),
          level: num(s.m), dangerLevel: num(s.o), margin: num(s.p),
          status, trend: String(s.s || ""),
          ts,
          updated: new Date(now).toISOString(),
        });
      }
      const out = json({
        updated: new Date(now).toISOString(),
        at_risk: atRisk.length,
        states: Object.entries(stateStats)
          .map(([state, count]) => ({ state, count }))
          .sort((a, b) => b.count - a.count),
        stations: atRisk,
      }, 200, { "cache-control": "public, max-age=300" });
      return out;
    }

    /* Active-alerts band: earthquakes that MATTER to Malaysia + current
     * flood risk, in one slim call. The MET earthquake feed is a global list
     * (~427 KB, 800+ events) - most of it is irrelevant (a M6.5 off Chile is
     * not a Malaysian alert). `n_distancemas` is the distance to the NEAREST
     * point in Malaysia ("838km S Pontian,Johor"), which makes the "does it
     * matter" filter exact: keep only events within 500 km AND within the
     * last 12 h. Flood risk reuses the /api/flood logic inline (status
     * WATCH + 24 h freshness + receding-Warning/Alert exclusion) so the band
     * and the flood section can never disagree. */
    if (url.pathname === "/api/alerts") {
      const denied = await guard(request, url, env);
      if (denied) return denied;

      /* KV-first: combined earthquake + flood summary from collect_alerts.py.
         The live branch below stays as the fallback when KV is empty. */
      try {
        const kv = await env.MYGOV_DATA.get("alerts");
        if (kv != null) {
          const parsed = JSON.parse(kv);
          if (parsed && Array.isArray(parsed.earthquakes) && parsed.flood) {
            return json(parsed, 200, { "cache-control": "public, max-age=60" });
          }
        }
      } catch { /* corrupt or missing KV value - fall through to live fetch */ }

      const now = Date.now();
      const EARTHQUAKE_FEED = "https://api.data.gov.my/weather/warning/earthquake";
      const EQ_RADIUS_KM = 500;
      const EQ_FRESH_MS = 12 * 3600 * 1000;

      let quakes = [];
      try {
        const res = await fetch(EARTHQUAKE_FEED, {
          headers: { "user-agent": UA },
          cf: { cacheTtl: 60, cacheEverything: true },
        });
        if (res.ok) quakes = await res.json();
      } catch { /* quakes stays empty - the band just shows floods */ }

      const relevant = [];
      for (const q of Array.isArray(quakes) ? quakes : []) {
        const dist = String(q.n_distancemas || "").match(/([\d,]+)\s*km/i);
        const km = dist ? Number(dist[1].replace(/,/g, "")) : null;
        if (km == null || km > EQ_RADIUS_KM) continue;
        const t = Date.parse(String(q.utcdatetime || "").replace(" ", "T") + "Z");
        if (!Number.isFinite(t) || now - t > EQ_FRESH_MS) continue;
        relevant.push({
          mag: num(q.magdefault),
          type: String(q.magtypedefault || ""),
          place: String(q.location_original || q.location || ""),
          lat: num(q.lat), lon: num(q.lon), depth: num(q.depth),
          km, dist: String(q.n_distancemas || ""),
          ts: t,
        });
      }
      relevant.sort((a, b) => b.ts - a.ts);

      /* Flood summary - same rules as /api/flood so both surfaces agree. */
      const FLOOD_FEED = "https://publicinfobanjir.water.gov.my/wp-content/themes/enlighten/data/latestreadingstrendabc.json";
      let flood = { at_risk: 0, danger: 0, warning: 0, alert: 0, top: [] };
      try {
        const res = await fetch(FLOOD_FEED, {
          headers: { "user-agent": UA },
          cf: { cacheTtl: 300, cacheEverything: true },
        });
        if (res.ok) {
          const rows = await res.json();
          const parseTs = s => {
            if (!s) return null;
            const m = String(s).match(/^(\d{2})\/(\d{2})\/(\d{4})[ T](\d{2}):(\d{2})/);
            if (!m) return null;
            return Math.floor(Date.parse(`${m[3]}-${m[2]}-${m[1]}T${m[4]}:${m[5]}:00+08:00`) / 1000);
          };
          const WATCH = new Set(["Danger", "Warning", "Alert"]);
          const RECEDING = new Set(["Receding", "Falling"]);
          const FRESH_MS = 24 * 3600 * 1000;
          const num = v => { const n = Number(v); return Number.isFinite(n) ? n : null; };
          const top = [];
          for (const s of Array.isArray(rows) ? rows : []) {
            const status = String(s.n || "");
            if (!WATCH.has(status)) continue;
            const trend = String(s.s || "");
            if (status !== "Danger" && RECEDING.has(trend)) continue;
            const ts = parseTs(s.q) ? parseTs(s.q) * 1000 : null;
            if (!ts || now - ts > FRESH_MS) continue;
            flood.at_risk++;
            if (status === "Danger") flood.danger++;
            else if (status === "Warning") flood.warning++;
            else flood.alert++;
            if (top.length < 5)
              top.push({
                name: String(s.b || ""), state: String(s.f || ""),
                level: num(s.m), dangerLevel: num(s.o),
                status, trend, ts,
              });
          }
          flood.top = top;
        }
      } catch { /* flood stays at zeros - the band just shows quakes */ }

      const out = json({
        updated: new Date(now).toISOString(),
        earthquakes: relevant,
        flood,
      }, 200, { "cache-control": "public, max-age=60" });
      return out;
    }

    /* Rapid KL service alerts (PULSE) - the latest post only.
     *
     * myrapid.com.my sits behind Incapsula (a JS-challenge WAF), so every
     * plain HTTP request - page, RSS, wp-json (which additionally returns
     * 401 rest_forbidden for anonymous reads) - fails. The r.jina.ai reader
     * proxy renders the page server-side and returns clean markdown, which
     * we parse for the newest alert (title, excerpt, timestamp, link). We
     * keep only the LATEST item - the dashboard shows one card, not a feed.
     *
     * Fetch strategy: the collect_rapid GitHub Action runs every 10 min from
     * GitHub's IP pool (jina's free tier rate-limits Cloudflare Worker
     * egress to null) and stores the result in KV under "rapid". This route
     * prefers that KV copy and only falls back to a live jina fetch on cold
     * start / KV cleared - where it may legitimately come back null, which
     * the deck simply omits. */
    if (url.pathname === "/api/rapid-alerts") {
      const denied = await guard(request, url, env);
      if (denied) return denied;

      /* KV copy first - fresh, reliable, unmetered by jina. */
      try {
        const kv = await env.MYGOV_DATA.get("rapid");
        if (kv != null) {
          const parsed = JSON.parse(kv);
          if (parsed && parsed.latest) {
            const out = json(parsed, 200, { "cache-control": "public, max-age=300" });
            return out;
          }
        }
      } catch { /* fall through to the live fetch */ }

      const JINA = "https://r.jina.ai/https://myrapid.com.my/pulse/service-alerts-on-pulse/";
      let latest = null;
      try {
        const res = await fetch(JINA, {
          headers: { "user-agent": UA },
          cf: { cacheTtl: 600, cacheEverything: true },
        });
        if (res.ok) {
          const md = await res.text();
          const MONTHS = "January|February|March|April|May|June|July|August|September|October|November|December";
          /* The reader renders each alert as:
           *   ### [Title](https://myrapid.com.my/.../)
           *   Excerpt text…
           *   [Read More »](url)
           *   August 11, 2026  11:00 am
           * Newest first - take the first block. */
          const head = String(md).split(/^### \[/m)[1];
          if (head) {
            const tm = head.match(/^([^\]]+)\]\((https?:\/\/[^)]+)\)/);
            if (tm) {
              const rest = head.split(/\[Read More/i)[0];
              const excerpt = rest.split("\n").slice(1).join(" ").replace(/\s+/g, " ").trim().slice(0, 240);
              const dm = head.match(new RegExp(
                "(" + MONTHS + ")\\s+(\\d{1,2}),\\s+(\\d{4})\\s+(\\d{1,2}):(\\d{2})\\s*(am|pm)", "i"));
              let ts = null;
              if (dm) {
                const MON = { january:0, february:1, march:2, april:3, may:4, june:5,
                  july:6, august:7, september:8, october:9, november:10, december:11 };
                let hh = Number(dm[4]);
                if (/pm/i.test(dm[6]) && hh < 12) hh += 12;
                if (/am/i.test(dm[6]) && hh === 12) hh = 0;
                /* Posted times are MYT (UTC+8, no DST). */
                ts = Math.floor(Date.UTC(Number(dm[3]), MON[dm[1].toLowerCase()],
                  Number(dm[2]), hh - 8, Number(dm[5])) / 1000);
              }
              latest = {
                title: tm[1].trim(),
                url: tm[2].trim(),
                excerpt,
                ts,
              };
            }
          }
        }
      } catch { /* latest stays null - the deck simply omits the card */ }

      const out = json({ updated: new Date().toISOString(), latest }, 200,
        { "cache-control": "public, max-age=600" });
      return out;
    }

    /* Air quality index for Malaysia's cities (Open-Meteo, free + keyless).
     *
     * The official APIMS feed (eqms.doe.gov.my) resets connections for
     * non-browser clients, so the dashboard uses Open-Meteo's air-quality
     * model instead - the same provider already approved for the weather
     * section. We poll one reading per major city and return the lot plus
     * the WORST and CLEANEST of the set, which is what the alert card shows
     * side by side. All timestamps are the model's hourly snapshot time
     * (Asia/Kuala_Lumpur). Edge-caches 10 min; the model updates hourly. */
    if (url.pathname === "/api/aqi") {
      const denied = await guard(request, url, env);
      if (denied) return denied;

      /* KV-first: collect_aqi.py fans out to Open-Meteo on a schedule and
         stores the ranked result. The live fan-out below remains the fallback
         for cold starts / KV cleared. */
      try {
        const kv = await env.MYGOV_DATA.get("aqi");
        if (kv != null) {
          const parsed = JSON.parse(kv);
          if (parsed && Array.isArray(parsed.stations) && parsed.stations.length) {
            return json(parsed, 200, { "cache-control": "public, max-age=600" });
          }
        }
      } catch { /* corrupt or missing KV value - fall through to live fetch */ }

      const CITIES = [
        ["Kuala Lumpur", 3.1390, 101.6869],
        ["Petaling Jaya", 3.1073, 101.6067],
        ["Shah Alam", 3.0733, 101.5185],
        ["Putrajaya", 2.9264, 101.6964],
        ["Penang", 5.4141, 100.3288],
        ["Johor Bahru", 1.4927, 103.7414],
        ["Ipoh", 4.5975, 101.0901],
        ["Kuching", 1.5535, 110.3593],
        ["Kota Kinabalu", 5.9804, 116.0735],
        ["Melaka", 2.1896, 102.2501],
        ["Kuantan", 3.8077, 103.3260],
        ["Seremban", 2.7246, 101.9343],
        ["Alor Setar", 6.1244, 100.3678],
        ["Kota Bharu", 6.1256, 102.2383],
        ["Kuala Terengganu", 5.3302, 103.1408],
        ["Miri", 4.3995, 113.9914],
        ["Bintulu", 3.1733, 113.0335],
        ["Langkawi", 6.3508, 99.8039],
      ];

      const stations = [];
      try {
        const lats = CITIES.map(c => c[1]).join(",");
        const lons = CITIES.map(c => c[2]).join(",");
        const q = new URLSearchParams({
          latitude: lats, longitude: lons,
          current: "us_aqi,pm2_5", timezone: "Asia/Kuala_Lumpur",
        });
        const res = await fetch(
          `https://air-quality-api.open-meteo.com/v1/air-quality?${q}`,
          { headers: { "user-agent": UA }, cf: { cacheTtl: 600, cacheEverything: true } });
        if (res.ok) {
          const raw = await res.json();
          const items = Array.isArray(raw) ? raw : [raw];
          for (let i = 0; i < CITIES.length; i++) {
            const item = items[i];
            if (!item || !item.current) continue;
            const cur = item.current;
            const aqi = cur.us_aqi;
            if (aqi == null) continue;
            stations.push({
              name: CITIES[i][0],
              aqi: Math.round(Number(aqi)),
              pm25: cur.pm2_5 == null ? null : Number(cur.pm2_5).toFixed(1),
              time: cur.time || null,
            });
          }
        }
      } catch { /* upstream error */ }

      stations.sort((a, b) => b.aqi - a.aqi);
      const out = json({
        updated: new Date().toISOString(),
        reading_time: stations.length && stations[0].time ? stations[0].time : null,
        stations,
        worst: stations[0] || null,
        cleanest: stations.length ? stations[stations.length - 1] : null,
      }, 200, { "cache-control": "public, max-age=600" });
      return out;
    }

    /* Malaysia Airports FIDS (flight information display) proxy.
     *
     * The official live arrivals/departures board on malaysiaairports.com.my
     * calls api.myairports.com.my with a public x-api-key embedded in its JS
     * bundle. The API sends no `access-control-allow-origin`, so browsers
     * cannot call it directly - same story as Nominatim above. Proxying here
     * keeps the key server-side (it is public, but living in one place makes
     * rotation trivial) and edge-caches the board so upstream sees one
     * request per TTL regardless of visitors. Boards refresh roughly every
     * minute on the site; 90 s is a fair middle ground. */
    if (url.pathname === "/api/fids") {
      const denied = await guard(request, url, env);
      if (denied) return denied;

      const code = url.searchParams.get("code") || "A";
      const terminal = url.searchParams.get("terminal") || "KLIA";
      const dayKey = url.searchParams.get("dayKey") || "0";
      // Strict allowlist - never interpolate user input into the upstream URL.
      // `terminal` is the 13 airports the board actually offers, not any
      // 16-char string: each unknown value was a fresh cache key costing up to
      // six paged upstream fetches.
      if (!/^[AD]$/.test(code)) return json({ error: "bad_code" }, 400);
      if (!FIDS_TERMINALS.has(terminal)) return json({ error: "bad_terminal" }, 400);
      if (!/^[0-9]$/.test(dayKey)) return json({ error: "bad_dayKey" }, 400);

      /* KV-first: the collect_fids workflow (GitHub IPs) uploads every board
         to the "fids" key every 10 min, because the upstream rate-limits
         Cloudflare Worker egress (429s - same as jina/myRapid). Serve the
         matching board from KV when present (today only - the collector
         fetches dayKey=0); live fetch is the fallback for other days. */
      const kvKey = `${code}|${terminal}`;
      const kvRaw = await env.MYGOV_DATA.get("fids");
      if (dayKey === "0" && kvRaw != null) {
        try {
          const kv = JSON.parse(kvRaw);
          const board = (kv.boards || {})[kvKey];
          /* Only a complete board is worth serving from KV. A truncated one
             (a failed page during collection) ends before the evening's
             flights and reads as "no more flights today", so fall through to
             the live fetch, which pages the whole day. */
          if (board && Array.isArray(board.flights) && !board.truncated &&
              (board.count == null || board.flights.length >= board.count)) {
            return json({
              count: board.count != null ? board.count : board.flights.length,
              returned: board.flights.length,
              truncated: board.count != null && board.flights.length < board.count,
              flights: board.flights,
              updated: kv.updated || null,
            }, 200, { "cache-control": "public, max-age=300" });
          }
        } catch { /* corrupt KV value - fall through to live fetch */ }
      }

      /* The upstream pages its results and returns them in schedule order, so
       * a single take=200 did not just "miss some" - on the busy terminals it
       * always dropped the END of the day. KLIA arrivals run to ~291 flights,
       * so the board stopped at roughly 17:45 and read as though it had frozen
       * mid-afternoon. Page until we have the count the upstream reports. */
      const PAGE = 200, MAX_PAGES = 6;
      const fidsUrl = skip => {
        const u = new URL(
          "https://api.myairports.com.my/passenger-fids/api/flights/search-flights");
        u.searchParams.set("code", code);
        u.searchParams.set("key", "all");
        u.searchParams.set("terminal", terminal);
        u.searchParams.set("dayKey", dayKey);
        u.searchParams.set("live", "true");
        u.searchParams.set("skip", String(skip));
        u.searchParams.set("take", String(PAGE));
        return u;
      };
      const upstream = fidsUrl(0);

      const cacheKey = new Request(
        `${url.origin}/api/fids?code=${code}&terminal=${terminal}&dayKey=${dayKey}`);
      const cache = caches.default;
      const hit = await cache.match(cacheKey);
      if (hit) return hit;

      /* The upstream intermittently drops a request (429/timeout), and one
         missed page used to truncate the board - which read as an empty
         evening board. Retry page 0 three times and later pages twice. */
      const pageJson = async (skip, tries) => {
        for (let a = 0; a < tries; a++){
          try {
            const p = await fetch(fidsUrl(skip), {
              headers: { "x-api-key": env.FIDS_API_KEY, accept: "application/json" },
              cf: { cacheTtl: 90, cacheEverything: true },
            });
            if (p.ok) return await p.json();
          } catch {}
          if (a + 1 < tries) await new Promise(r => setTimeout(r, 800));
        }
        return null;
      };
      const data = await pageJson(0, 3);
      if (!data) return json({ error: "upstream_unreachable" }, 502);

      /* Page 1 tells us the real total; fetch the rest in parallel. A failed
       * page is skipped rather than failing the board - a partial board beats
       * no board, and `truncated` says which one the client got. */
      const statuses = (data.flightStatuses || []).slice();
      const total = Number(data.count) || statuses.length;
      if (statuses.length && total > statuses.length) {
        const pages = Math.min(Math.ceil(total / PAGE), MAX_PAGES);
        const rest = await Promise.all(
          Array.from({ length: pages - 1 }, (_, i) =>
            pageJson((i + 1) * PAGE, 2)));
        for (const p of rest)
          if (p && Array.isArray(p.flightStatuses)) statuses.push(...p.flightStatuses);
      }

      // Slim the payload: the dashboard renders a board, not codeshares and
      // baggage belt metadata. Keeping only the columns the UI needs trims a
      // ~1.5 MB response to a few KB and makes the client simpler.
      const slim = statuses.map(f => ({
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
      /* A page that failed above is skipped rather than failing the board, so
         `slim` can be short of `total`. Serve it - a partial board beats no
         board - but do NOT cache it: a single transient upstream hiccup would
         otherwise be frozen under the same key as a complete board and served
         to everyone for the full TTL, long after the upstream recovered. Only
         a whole board is worth keeping. */
      const partial = slim.length < total;
      const out = json({
        count: total,
        returned: slim.length,
        truncated: partial,
        flights: slim,
      }, 200, {
        "cache-control": partial ? "no-store" : "public, max-age=90",
      });
      if (!partial) ctx.waitUntil(cache.put(cacheKey, out.clone()));
      return out;
    }

    /* IP-based location fallback.
     *
     * Browser geolocation (getCurrentPosition) is unreliable on desktops -
     * no GPS, and Chrome/Firefox depend on Google's network-location service
     * which is often blocked or slow. Cloudflare populates request.cf with
     * the visitor's IP-derived location (city, region, country, lat/lon), so
     * this route hands that to the app as a fallback. Same-origin only. */
    if (url.pathname === "/api/geoip") {
      const denied = await guard(request, url, env);
      if (denied) return denied;
      const cf = request.cf || {};
      const out = {
        city: cf.city || null,
        region: cf.region || null,
        country: cf.country || null,
        latitude: cf.latitude != null ? Number(cf.latitude) : null,
        longitude: cf.longitude != null ? Number(cf.longitude) : null,
      };
      // Only useful if we actually got a coordinate pair.
      if (out.latitude == null || out.longitude == null)
        return json({ error: "no_geoip" }, 404);
      return json(out, 200, { "cache-control": "public, max-age=3600" });
    }

    /* Collector data from KV.
     *
     * slow.json / health.json / radar.json / feed.xml are written by the
     * GitHub Action collectors. They used to be committed to git (causing
     * constant push races with manual edits); now they live in KV and the
     * Worker prefers KV, falling back to the static file in public/ (which
     * stays as a cold-start copy). The SEO snapshot (seo_snap) is spliced
     * into index.html's <noscript> block at request time, so crawlers still
     * see fresh headline values without any bot commits. */
    const KV_FILES = {
      "/slow.json":   { key: "slow",  type: "json" },
      "/series.json": { key: "series", type: "json" },
      "/health.json": { key: "health", type: "json" },
      "/radar.json":  { key: "radar",  type: "json" },
      "/prices.json": { key: "prices", type: "json" },
      "/geo.json":    { key: "geo",    type: "json" },
      "/insights.json":  { key: "insights",  type: "json" },
      "/forecasts.json": { key: "forecasts", type: "json" },
      "/transport_history.json": { key: "transport", type: "json" },
      "/cars.json": { key: "cars", type: "json" },
      "/tourism.json": { key: "tourism", type: "json" },
      "/travel.json":  { key: "travel",  type: "json" },
      "/rapid_alerts.json": { key: "rapid", type: "json" },
      "/traffic.json":     { key: "traffic", type: "json" },
      "/feed.xml":    { key: "feed",   type: "text" },
    };
    if (KV_FILES[url.pathname]) {
      const { key, type } = KV_FILES[url.pathname];
      const v = await env.MYGOV_DATA.get(key);
      if (v != null) {
        const body = type === "json" ? v : v; // KV.get returns the raw string
        const headers = {
          "access-control-allow-origin": "*",
          "x-content-type-options": "nosniff",
          "cache-control": "public, max-age=600",
        };
        headers["content-type"] =
          type === "json" ? "application/json; charset=utf-8"
                          : "application/rss+xml; charset=utf-8";
        return new Response(body, { status: 200, headers });
      }
      // Fall back to the static copy committed in public/ (cold start or KV
      // cleared). Asset router serves it with its own headers.
      return env.ASSETS.fetch(request);
    }

    /* index.html SEO snapshot splice.
     *
     * The <noscript> block between <!-- SEO:SNAP --> markers used to be
     * rewritten + committed by the collector (another race source). Now the
     * collector writes the snapshot to KV (`seo_snap`); the Worker splices
     * it into the served HTML so crawlers see fresh values while git stays
     * human-only. Falls back to whatever is in the committed file. */
    if (url.pathname === "/" || url.pathname === "/index.html") {
      const snap = await env.MYGOV_DATA.get("seo_snap");
      if (snap != null) {
        const res = await env.ASSETS.fetch(request);
        if (res.ok && (res.headers.get("content-type") || "").includes("text/html")) {
          const html = await res.text();
          /* Two things worth keeping here:
           *
           * 1. The replacement is a FUNCTION, not a string. String.replace
           *    interprets $&, $` and $' in the replacement, so a snapshot
           *    containing them would splice surrounding page content back
           *    into itself. A function replacement is taken literally.
           * 2. The snapshot is markup by design (it is the <noscript> block),
           *    so it cannot be escaped - but it must stay inert. Anything
           *    that executes is stripped: the collector is trusted today,
           *    and this keeps a leaked KV token from turning the homepage
           *    into a script host. CSP already blocks inline and non-'self'
           *    scripts; this is the belt to that pair of braces. */
          const inert = String(snap)
            .replace(/<\s*(script|iframe|object|embed|link|meta|base)\b[\s\S]*?>/gi, "")
            .replace(/<\/\s*(script|iframe|object|embed)\s*>/gi, "")
            .replace(/\son[a-z]+\s*=/gi, " data-stripped=");
          const out = html.includes("<!-- SEO:SNAP -->")
            ? html.replace(
                /<!-- SEO:SNAP -->[\s\S]*?<!-- \/SEO:SNAP -->/,
                () => `<!-- SEO:SNAP -->\n${inert}\n<!-- /SEO:SNAP -->`)
            : html;
          // Preserve the asset's headers (CSP, HSTS, X-Frame-Options, and the
          // _headers cache-control) - building a fresh Response here used to
          // drop every security header from the served homepage.
          const headers = new Headers(res.headers);
          headers.delete("content-length");  // body changes; length is stale
          return new Response(out, { status: 200, headers });
        }
        return res;
      }
    }

    // Everything else is a static asset. Security headers for those come from
    // public/_headers - the asset router serves them without running this
    // Worker, so setting headers here would have no effect.
    return env.ASSETS.fetch(request);
  },
};
