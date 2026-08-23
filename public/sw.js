/* mygov service worker - app shell precache + offline API fallback.
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
/* BUMP whenever /index.html, /app.js or /styles.css changes. Since v15 they are precached
   SHELL_ASSETS served cache-first, so without a bump a returning visitor keeps
   running the previous build indefinitely - the shell only refetches when the
   cache name changes. v16: rapidCard href hardening + the summariser.
   v17: itemGeo / "Where it's cheapest".
   v18: animated weather sky, radar collection stamp, themed election
   seat search + state filter.
   v19: on-demand Chart.js/Leaflet, series.json split, "Malaysia at a Glance"
   rename, per-condition weather icons. The cache name keeps the mygov- prefix
   deliberately: it is an internal key, and renaming it only orphans caches.
   v20: brief icon, holiday/school chip dropdowns.
   v21: live traffic feed (traffic.json in the data-bundle exclusion).
   v22: traffic marquee items - separators, clickable t.co links, slower
   scroll.
   v23: security + a11y pass - safeUrl on radar source links, honest roles on
   the vehicle/flood/route chips, keyboard activation for metro stations, and
   a real pause control on the traffic ticker.
   v24: Trend Radar claim/fact_details modal, claim previews, status filters,
   relative freshness, and filter/empty-state handling.
   v25: Merdeka flag splash, seasonal motif layer, redrawn glyph set, paired
   section cards, transport block row spanning, trend radar arrows kept in
   viewport, methodology endpoint URLs, per-section share buttons with live
   figures, and the travel share button joining its row.
   v26: daily ridership by service on Public Transport - a ridership_headline
   card (trips taken, not unique passengers) with week-on-week moves and a
   share bar, plus the section methodology noting the new source.
   v27: the ridership card drops Rapid Bus Kuantan (its series is not being
   updated), and the FX hero shows the newest of BNM's four daily references
   (09:00/11:30/12:00/17:00) instead of always the 12:00 rate, with the
   collector now running just after each reference.
   v28: fuel card + methodology name the Thursday weekly-update cadence.
   v29: Live Vehicles open on the Rapid KL feed by default, with network
   chips for KTMB trains / Rapid Penang / All, and the Penang route-name
   load deferred until that feed is actually shown.
   v30: Public Transport drops the static per-route scheduled-trip tables
   (and the route search that only filtered them) - actual daily ridership
   now lives in the ridership card.
   v31: each transport network's route/stops/trips KPIs live in their own
   titled card instead of a bare KPI row.
   v32: Rapid Penang joins the transport network cards (GTFS-static, plain
   row-per-trip counts) with its own filter chip and stops coverage.
   v33: the ridership card is renamed "Daily ridership by service" to match
   data.gov.my's own dashboards - it was mislabelled as trips.
   v34: the All stops card asks for location once when Public Transport
   opens and shows nearest stops by default, no tap required.
   v35: nearest stops are capped at 50 km so a KL visitor no longer sees
   Rapid Penang's "nearest" stops from 300 km away.
   v36: FIDS stops serving truncated boards - the collector retries failed
   pages, the Worker falls back to a live full-day fetch instead of a short
   board, and a partial board is labelled rather than looking empty.
   v37: nearest stops reuse the app's single detected location (weather's
   GPS/IP fix) instead of asking the browser for a second fix.
   v38: FIDS status labels are direction-aware - arrivals no longer show
   "check-in open" (COP on the A board is the arrival process open), and
   the missing departure gate/check-in codes are labelled.
   v39: earthquakes now expire after 3 hours (still within 500 km of
   Malaysia) instead of 24, so a replayed or old quake never lingers.
   v40: Chrome AI upgrades - in-memory summary caching, structured payload extraction, Ask MyGov natural language assistant, Morning Citizen Brief, and ELI5 plain language metric explainers.
   v41: fix Ask MyGov container mount placement and add instant client-side open data matcher fallback for universal browser accessibility.
   v42: wire up ? metric explainers universally across all sections with fallback plain-language breakdowns.
   v43: implement aiSpeak speech synthesis engine with voice selection and speech cancel/toggle.
   v44: fix action button contrast and harden voice synthesis fallback and browser queue resume.
   v45: enforce high-specificity dark theme contrast on action links and ensure synchronous speech synthesis invocation.
   v46: intelligent multi-domain search fallback indexer and enhanced button icon styling.
   v47: restore complete AI runtime helpers and prevent fallback exception loop.
   v48: fully bind action and voice buttons to site design system .btn / .btn-a theme tokens.
   v49: intelligent metric-extracting open data question answering engine for precise factual responses.
   v50: state-level sub-national demographic resolution for population queries.
   v51: UI/UX overhaul Phases 1-3, location bookmarks, section pinning & reordering, bus route pagination tray, table CSV copy, persistent accordions, and variable reference fixes.
   v52: Universal top-level active warnings alert banner elevated above traffic ticker and live vehicle feeds.
   v53: Automatically load and rank nearest public transport stops across all networks by default.
   v54: Segregate school holidays (KPM calendar) and state-specific vs nationwide public holidays in Ask MyGov AI assistant.
   v55: Location search query refinement and state demographic enhancements.
   v56: Redesign website icons to modern design standards with SVG favicon and high-DPI PWA assets.
   v57: Warm the live vehicle feeds on idle so the card is populated before the user scrolls to Transport.
   v58: Breaking news ranked by a news-desk editor pass with impact tier and what/who/impact bullets on the card.
   v59: Breaking feed capped at 10 editor-picked stories with urgency tier, editor summary and assigned category.
   v60: Drop the source count from trend cards; show every outlet in the detail sheet even when its URL is unresolved.
   v61: Remove Ask MyGov and My Day Brief. The assistant answered from a
   hand-written regex table with figures baked into the source, so on the
   ~99% of devices without Gemini Nano it stated stale numbers as official
   ones; the brief re-summarised the Daily Brief band it was attached to.
   v62: Implement Sovereign Ruby & Gold Bunga Raya (National Flower) brand icon redesign suite.
   v63: Ensure 100% transparent background across all vector SVGs and PNG assets with drop-shadow brand mark styling for light/dark theme adaptability.
   v64: Add multi-resolution transparent favicon.ico (16x16, 32x32, 48x48) and favicon-32/16 PNG fallbacks.
   v65: Ensure 100% solid opacity across flower interior (petals, navy core, gold veins) with outer transparent background for light and dark themes.
   v66: Header brand mark scaled up against the title lockup (42px desktop,
   38px under 620px, matching intrinsic img attrs), and the active-warnings
   band drops its duplicate warning emoji - the .warn-top-tag badge already
   carries the icon.
   v67: TomTom traffic incidents collector - traffic_incidents.json added to
   the data-bundle exclusion list (structured urban/destination incidents,
   complementing the highway-only InfoTrafikGZ feed).
   v68: Traffic incidents panel - region chips, KPI chips and incident list
   under the marquee, auto-selected from the location pipeline (geo.osm state),
   with a saved region choice in localStorage.
   v69: Traffic incidents panel freshness - feed older than 6h hides the panel
   entirely, and ended incidents (past endTime) are dropped from the list and
   KPI counts, so yesterday's jams never show as today's.
   v70: TomTom incidents merged INTO the marquee instead of a separate panel -
   no new section. Region-scoped (visitor's state), active-only, fresh-only;
   collector now also carries per-incident events descriptions ("Queuing
   traffic") and magnitudeOfDelay.
   v71: Drop the top-of-page active-warnings band (v52). The sticky nav already
   carries a Warnings entry with a live count badge and status dot, and the
   hazard strip's first tile opens on "N active alerts" - the band was a third
   copy of the same number, and unlike the nav it scrolled away. It existed
   because Live Vehicles was rendering above Warnings: a stray </section> in
   index.html left #live-sub outside #transport, and applySectionOrdering()
   re-appends every section to #main, so the orphan floated to the top. The
   sub-block is back inside Transport, which is the actual fix.
   Also v71, TomTom: the collector's iconCategory map was hand-written and
   shifted, so 875 of 1,084 incidents - ordinary jams - were published as
   "Accident" and every road closure as "Road works". Replaced with TomTom's
   published v5 taxonomy, with a CI assert so a name outside it fails the run.
   The feed no longer ships polylines it never drew (905 KB -> 72 KB),
   collapses one jam reported on N adjacent segments (and in both directions)
   into one, and ranks numbered roads above housing-estate lanes. The ticker
   picks the visitor's region from their coordinates against the region
   bboxes instead of a state lookup that put Terengganu in Kuantan and every
   uncovered state in the Klang Valley, and it re-picks whenever the location
   pipeline moves - it used to run once at boot, before geo resolved, so
   nearly everyone got the Klang Valley. Both feeds now render through one
   painter, so whichever lands second no longer wipes the other.
   Also v71, earthquakes: the alert was mechanically fine - feed fetches,
   n_distancemas parses, filters apply - but its 12-hour window was set against
   a phenomenon that happens ~1.5 times a month within 500 km, so a card was on
   screen roughly 0.3% of the year and nobody could tell working from broken.
   The deck now carries seven days; only the last 24 hours count towards the
   nav badge, which still means "right now". Four files documented four
   different windows (3h, 12h, 24h, "strictly the last 24h"); they now all
   state the one that is implemented.

   Also v71, location: picking a place by hand kept the previous fix's OSM
   state and wrote it back to localStorage, so choosing Kuching while the last
   fix was in Selangor left the visitor's state as Selangor - which is what the
   holiday chips read. A pick now clears the stale position and resolves the
   chosen place's own coordinates and state. The hero's dead "selected area"
   text became a real "use my location" button (previously there was no way
   back to auto-detect once you had picked), the weather card's "change" button
   is named for what it does rather than sharing a label with a different
   action, and the observation time stopped overwriting that whole control.
   Also v71, USGS: MET's earthquake feed is no longer live. Checked 15 Aug 2026
   with the cache bypassed (cf-cache-status: BYPASS, so this is the origin's
   own answer): 836 events whose newest was six days old, and no sign of that
   morning's M6.9 at Pematangsiantar - 268 km from the Perak coast, well inside
   the radius this page filters on. Over the preceding 30 days MET listed 2
   events within 500 km; USGS listed 8. USGS now runs as the live source
   through a new /api/quakes Worker proxy (earthquake.usgs.gov is deliberately
   not in the connect-src allowlist, and the proxy also edge-caches one fetch
   of a 1.6 MB worldwide feed for every visitor); MET is merged in for what it
   does carry, and duplicates are collapsed on a two-minute/150 km tolerance.
   Cards name their source.

   Also v71, Trending folds. It was 430px of carousel between the nav and the
   first data section; folded to its heading and freshness stamp it gives back
   ~290px, and the choice is remembered.
   v72: Two layout fixes.
   The trend/breaking detail sheet's title was the only head child that could
   shrink and the only one without flex-grow, while each pill reserved 44px to
   clear the ✕ button. On a 375px screen that left the headline 154px and eight
   lines tall - a narrow column beside a mostly empty header. The ✕ clearance
   is now the head's own padding, the title has a 220px floor, and the pills
   wrap beneath it.
   The touch-target rule for disclosure summaries used `padding:9px 0`, which
   also zeroed the horizontal padding of the summaries that had some - and the
   table disclosures ("All locations table", places, election, ridership) use a
   full .card-h as their summary. On touch their heading sat flush against the
   card border while the table below stayed inset. Now vertical-only.
   v73: The postcode field was the only flexible item in its row, so the
   "2,932 postcodes · type to filter" counter took its width straight out of
   the input - 391px down to 179px the moment it appeared. The counter drops
   the "type to filter" half (the placeholder already says it), the field gets
   a 180px floor, and the counter ellipsises before the field gives. Also
   "1 matches" -> "1 match".
   v74: The traffic ticker never actually showed its TomTom half.
   The marquee animates each of two duplicated .traffic-run spans by -50% of
   its OWN width, on the belief that "the run is 2x content by construction" -
   but the painter puts the whole list in each of the two runs, not twice
   inside one. So each run slid half its width and snapped back, and only the
   first half of the list ever crossed the window. The highway posts were ~79%
   of a 12,587px strip, so they looped forever and the TomTom incidents in the
   tail were unreachable no matter how long you watched. Now -100%, which is
   one full run: when the first has left, the second is exactly where it began.
   The two sources are also interleaved rather than concatenated, so one of
   each is on screen within seconds instead of 87.
   Nothing older than two hours rides the strip now, from either source (was
   3h for the highway posts and 6h for the TomTom feed), and the collector
   moved to hourly 06:00-23:00 MYT so that rule does not just hide the layer.
   Jams also outrank roadworks: ranking roadworks higher read as "severity" and
   was wrong for a live feed - a roadworks layout is the same for weeks, a jam
   is what is happening now. Measured 15 Aug, 22:45: Klang Valley shipped 19
   active roadworks and 21 already-ended jams; Penang shipped 30 of 40 as
   roadworks. The collector now holds two thirds of each region's slots back
   from roadworks, which never expire and would otherwise crowd out the rest.
   Note: this bump is now enforced by .github/workflows/ci.yml, which fails
   the build if app.js or styles.css changed and VERSION did not.
   v75: Two hazard-deck fixes, one of which is this bump.
   The quake-age fix (3ba946b: a quake past 24 h drops its alert tint and
   leads with its age) shipped to the origin without a VERSION bump. CI caught
   it and failed, but Pages deploys off the branch regardless of CI, so the
   fixed app.js sat at the origin while every returning visitor kept being
   served the pre-fix copy out of the v74 shell cache - cache-first, no expiry,
   no remote lever. Two days on, the 15 Aug M6.9 was still wearing a red
   stripe with no age on it for anyone who had visited before: the fix was
   live and invisible at the same time. This bump is what actually delivers
   it. A red CI run on main means the shell needs a bump, not a re-deploy.
   Also v75: MET re-issues a standing bulletin per validity window instead of
   amending one row, so the strong winds and rough seas warning arrived three
   times on 17 Aug with identical text and drew three identical storm cards.
   Identical heading, body and instruction now collapse to one card carrying
   the widest window in force.
   v76: A quake past the alert window leaves the deck entirely.
   v75 muted its stripe, which was not enough: a two-day-old event still sat
   in a carousel headed "everything currently on issue", between a live storm
   warning and a river above its danger mark, and read as one more thing
   going wrong. The deck now carries only quakes inside EQ_ALERT_MS; older
   ones move to a collapsed "Recent earthquakes" list directly below it,
   beside the all-clear notices. Nothing is dropped - at ~1.5 events a month
   within 500 km, expiring them at 24 h would leave the earthquake feature
   empty on ~99.7% of days, which is what the week-long window exists to
   avoid. The empty-deck line changes with it: it can no longer say there
   have been no quakes in seven days while listing some underneath.
   v77: The earthquake window is 24 hours, and there is only one of them.
   v76 kept older quakes on the page in a collapsed list. They should not be
   on the page at all: if nothing has happened, that is the answer, and the
   section already works that way for warnings and river gauges. The week was
   justified on a scarcity measured against MET's feed while it was stale -
   the fault USGS was added to fix. Re-measured against USGS over the year to
   17 Aug 2026, same 500 km filter: 88 events on 76 separate days, so a
   24-hour window has something to show about one day in five. EQ_ALERT_MS is
   gone with the split - badge and deck count the same events now, and the
   collapsed "Recent earthquakes" block v76 added is removed.

   v78: /series.json and /hotel.json join the never-intercepted data bundles.
   They were absent, so the SW served them cache-first and a returning
   visitor's exchange-rate card stayed on the copy their first visit cached -
   the 2026-08-10 slow.json regression again, on the bundle finance moved to.
   The bump also evicts the stale copies already sitting in v77's shell.
   v79: the live FX fallback path (used when KV is cold, e.g. a deploy window)
   now keeps all 9 currencies (cny/jpy/thb/aud were truncated to 6 columns,
   blanking those lines in the chart until the next KV push). */
/* v80: Phase-0 CLS/a11y pass - hero slots ship pre-rendered skeletons (wx
   prose, brief, holiday row, two-card travel skeleton), Trend Radar ships
   folded with the state mirrored server-side via the mygov_rf cookie, radar
   init moves off the critical boot path, marquee clone is inert.
   v83: Phase-2 interactivity - sortable tables, CSV copy, chart crosshair
   (see the v83 note below).
   v84: Phase-3 - .wx-t-min min-temp color uses --fg-2 (the old #93a0b6
   failed 2.26:1 on the light theme's tinted today-card; --fg-2 passes
   5.91:1 dark / 6.62:1 light on that same background). */
const VERSION    = "mygov-v85";
const SHELL      = `${VERSION}-shell`;
const API_CACHE  = `${VERSION}-api`;
const KEEP       = new Set([SHELL, API_CACHE]);

const SHELL_ASSETS = [
  "/",
  "/index.html",
  "/app.js",
  "/styles.css",
  "/manifest.webmanifest",
  "/favicon.svg",
  "/favicon.ico",
  "/icons/favicon-32.png",
  "/icons/favicon-16.png",
  "/icons/icon.svg",
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
    // addAll is atomic - one bad URL fails the whole install, so add
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

/* Data requests: network first, last-good copy as the offline fallback. */
const isApi = url =>
  url.hostname === "api.data.gov.my" ||
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
        // upstream or via our proxy) - an 8 MB archive per agency would blow
        // through the Cache Storage quota for data the page immediately
        // reduces to a small summary anyway.
        const isZip = url.pathname.startsWith("/gtfs-static") ||
                      url.pathname.startsWith("/api/gtfs");
        if (fresh.ok && !isZip) cache.put(request, fresh.clone());
        return fresh;
      } catch (err) {
        const hit = await cache.match(request);
        if (hit) {
          // Tag it so the page can show an "offline - showing cached" state.
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

  /* Cross-origin sub-resources - map tiles - are left to the browser.
   *
   * A worker that calls respondWith() re-issues the request as its own
   * fetch(), and a fetch() from a worker is policed by `connect-src`, not by
   * the `img-src` that governs the <img> the page actually made. The tile
   * host is deliberately on img-src only, so every tile was blocked inside
   * the worker, and the catch below turned each one into an empty 503 - a
   * blank basemap on every visit. Nothing here wants to cache them anyway:
   * the branch below only stores same-origin responses. */
  if (url.origin !== self.location.origin) return;

  /* Data bundles (slow/health/radar/prices/geo/insights/forecasts/feed) are NEVER intercepted. The app
   * fetches them with cache:"no-store", and KV serves them with a 10-min
   * edge TTL, so they are already fresh. A SW-cached copy would go stale:
   * this exact bug regressed the FX card to Friday's rates on 2026-08-10
   * because the cache-first branch below served a slow.json cached during
   * an earlier visit, ignoring the no-store hint (caches.match ignores
   * cache mode). Offline fallback for these is the app's live-API chain,
   * not the SW.
   *
   * series.json and hotel.json were missing from this list and so hit the
   * cache-first branch below - the same regression, on the bundle the FX
   * card actually reads since v19 split finance out of slow.json. A visitor
   * kept whatever series.json their first visit cached until the next
   * VERSION bump, which is why the exchange-rate card could sit days behind
   * KV while a hard reload changed nothing. Anything the collectors publish
   * belongs here; only the shell does not. */
  if (url.pathname === "/slow.json" || url.pathname === "/series.json" ||
      url.pathname === "/health.json" ||
      url.pathname === "/radar.json" || url.pathname === "/prices.json" ||
      url.pathname === "/geo.json" || url.pathname === "/hotel.json" ||
      url.pathname === "/insights.json" || url.pathname === "/forecasts.json" ||
      url.pathname === "/transport_history.json" || url.pathname === "/cars.json" ||
      url.pathname === "/tourism.json" || url.pathname === "/travel.json" ||
      url.pathname === "/rapid_alerts.json" || url.pathname === "/traffic.json" ||
      url.pathname === "/traffic_incidents.json" ||
      url.pathname === "/feed.xml") return;

  // Everything else (icons, vendor scripts): cache first.
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
