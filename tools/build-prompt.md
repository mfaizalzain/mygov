# mygov dashboard — master build prompt (consolidated 2026-08-09)

Build/refine the mygov dashboard: a beautiful, user-friendly PWA for Malaysia's
Government Open API (api.data.gov.my) plus MoH health data. Live at
mygov.faizalmzain.com (Cloudflare Worker static assets) — a product, not a
prototype. Push to main auto-deploys.

---

## Development workflow — USE the mygov MCP CONNECTOR
You have MCP tools `mygov_*` available (server: mygov). Use them THROUGHOUT
development, not just for final wiring:
- Before writing any fetch code, call mygov_weather_forecast,
  mygov_weather_warning, mygov_data_catalogue, mygov_opendosm,
  mygov_gtfs_static_summary, mygov_gtfs_realtime to inspect the REAL response
  shapes. Do not assume field names — verify them from live data.
- When a filter/query doesn't work, test variations through the MCP tools
  until you find the working syntax, then hardcode that.
- The weather API has NO coordinates — only location_id + location_name.
- Validate every section's data requirements against a live tool call before
  building its UI. The API rate limit is 4 req/min per family — the MCP server
  throttles automatically, so space out your exploration calls.

---

## Visual design (non-negotiable)
- Premium dark theme, Linear/Vercel-grade polish. NOT a generic bootstrap look.
- Design system first: CSS variables for a cohesive palette — deep
  slate/charcoal backgrounds with layered elevation (cards subtly lighter than
  the page), ONE accent color used sparingly (e.g. vivid teal or indigo),
  semantic colors for success/warning/danger states.
- Typography: system font stack with careful hierarchy — bold display weight
  for section titles, tight tracking on numbers (tabular-nums for all figures),
  consistent spacing scale (4/8/12/16/24/32).
- Cards: soft borders (1px rgba), subtle shadows, rounded corners (12-16px),
  hover states that lift slightly.
- Micro-interactions: smooth color/transform transitions (~150-200ms), animated
  number counters on KPIs, skeleton shimmer while loading, fade-in sections.

---

## Layout & UX
- Hero header: dashboard name + tagline, big "last updated" badge, prominent
  Refresh button with spinning icon while fetching.
- Sticky nav with anchor links to each section; smooth scroll.
- KPI summary row at top (today's max temp across Malaysia, latest RON95 price,
  live vehicles now, etc.) — real numbers, not placeholders.
- Each data family = a section with: icon + title + short plain-English
  description, then its charts/tables.
- Charts: Chart.js styled to match the theme — gradient fills, rounded bars,
  no default grid clutter, hover tooltips with exact values, styled legend.
- Tables: sticky header, subtle zebra striping, right-aligned numbers,
  monospace digits, sortable where sensible, "show top N" to avoid 1000-row
  dumps.
- Search/filter: fuel/CPI with a date-range or "last 6 months / 1 year / all"
  toggle.

---

## Location-aware weather
- On first load, if the user grants permission, request position via
  navigator.geolocation (timeout ~8s, graceful decline — never block the
  dashboard on it).
- Reverse-geocode via Nominatim (https://nominatim.openstreetmap.org/reverse
  ?format=json&lat=..&lon=..&zoom=10) with a proper User-Agent header
  ("mygov-dashboard/1.0"). Call once on load; respect its 1 req/sec limit.
  NOTE: Nominatim has no CORS and browsers can't set User-Agent — the
  /api/reverse Worker proxy does this server-side (rounds coords to ~1km,
  edge-caches a day). Keep that architecture; degrade to manual search if the
  proxy is down.
- Extract state/district/town from the result, match against
  location__location_name with case-insensitive fuzzy matching, preferring
  district (Ds###) > town (Tn###) > state (St###). On ties show a top-3
  "did you mean…?" picker; on no match fall back to a manual search combobox.
- Show a "📍 Near you: <Location>" chip in the weather header with a "use my
  location" / "change" affordance, and a "location off" state for denied
  permission. Offline falls back to the last cached location match.

---

## PWA requirements (installable + offline)
- manifest.webmanifest: name "mygov", short_name, description, start_url "/",
  display "standalone", theme_color + background_color matching the palette,
  icons 192x192 and 512x512 PNG (on-brand, no external downloads).
- Service worker (sw.js):
  - Pre-cache app shell (index.html, sw.js, manifest, icons) on install.
  - Cache-first for static assets; stale-while-revalidate for api.data.gov.my
    and MoH responses (cached data shows offline with a "offline / last
    updated" indicator).
  - Versioned cache; on activate, purge old caches. Handle fetch errors
    gracefully (fall back to cache, never crash).
  - Never cache opaque/cross-origin responses.
- Register SW from index.html; add <link rel="manifest">, <meta
  name="theme-color">, apple-touch-icon; capture beforeinstallprompt and show
  an "Install app" button in the header when available.
- All files committed alongside index.html — pure static, no build step.

---

## Weather warnings strip (under the forecast section)
- Fetch mygov_weather_warning on load and render active warnings as alert
  cards: title (heading_en / title_en), text_en description, and valid_from →
  valid_to timestamps. Style: amber/red accent border, severity-appropriate
  icon. Empty state: a quiet green "No active warnings" chip. Warnings update
  on refresh.

---

## OpenDOSM (economic indicators — DOSM)
- Source: open.dosm.gov.my; API is the same /opendosm endpoint on
  api.data.gov.my via mygov_opendosm.
- KPI cards: latest CPI index, Industrial Production Index (ipi), Producer
  Price Index (ppi), Index of Wholesale & Retail Trade (iowrt) — real numbers.
- Charts (one per dataset, "last 6 months / 1 year / all" toggle):
  - CPI: line chart of index over time (cpi_core), colored by division.
  - IPI: line chart of index + seasonally-adjusted index_sa.
  - PPI: line chart of index (ppi).
  - IOWRT: line chart of volume vs volume_sa (iowrt).
- Tables for demographics (deaths, fertility, marriages): filterable by year
  range, sex/age_group where present, "show top N" default.
- Only show datasets that return data — verify each with a live mygov_opendosm
  call first. pricecatcher does NOT work via /opendosm — skip it.

---

## Data freshness policy (hard rule)
- Applies to the dataset's LAST-UPDATED date, NOT historical depth. Long
  history is fine; a series nobody updates is not.
- EXCLUDE any dataset whose latest date is more than 2 years old (audit done
  2026-08-09 — re-verify at build time with a sort=-date call).
- STALE — do NOT build sections for these:
  - births (last update 2023-07-31 — 3.0 yr frozen)
  - mnha (2022-01), marriages (2022-01), population_state (2023-01),
    deaths (2024-01), fertility (2024-01)
  - arrivals (tourism, last update 2024-10-01) and passports (2024-10-01) —
    22 months frozen, effectively abandoned. Skip the tourism section.
- FRESH — keep: fuelprice (3d), cpi_core/ppi (69d), iowrt (100d), ipi (130d),
  exchangerates (161d), population_malaysia (220d), interestrates (251d),
  MoH health (daily).
- Every section header shows a "data as of <date>" line — if the data is
  older than 6 months, add a muted "⚠️ may be delayed" note.

---

## Finance & tourism (all VERIFIED working datasets)
Verify each with a live mygov_data_catalogue call before wiring its UI; only
build sections for datasets that return data. All time-series → default
sort=-date (they come oldest-first otherwise).
- Exchange rates (exchangerates): line chart of MYR vs 4-6 key currencies —
  USD, GBP, EUR, SGD, IDR — with "6 months / 1 year / all" toggle and a
  currency picker. Tabular-nums; tooltip shows rate + date.
- Interest rates (interestrates): line chart of OPR (bank=commercial,
  rate=opr) over time + small table of latest rates per bank type.
- Postcode lookup (poskod): searchable reference table (postcode → city →
  state), not a chart — small utility card with inline search. (Static
  reference data — freshness rule does not apply; it's a lookup table.)
- Tourism (arrivals/passports) is EXCLUDED per the freshness policy — last
  updated 2024-10-01. Do not build it even though the data exists.

---

## Health section (MoH KKMNOW — data on GitHub, updated daily)
- Source: raw.githubusercontent.com/MoH-Malaysia/kkmnow-data/main/*.parquet
  (MIT, CORS open — fetch directly in the browser). Parse parquet with the
  hyparquet JS library (~10KB, no build step).
- Fetch metadata_updated_date.json first and show a "Health data updated:
  <latest>" line in the section header.
- Blood donations (blood_02_timeseries.parquet: date/state/daily/daily_7dma):
  line chart of daily donations for Malaysia + state dropdown (16 states),
  7-day moving average overlay. KPI: latest daily + 7d total.
- Blood stock (blood_01_stock_timeseries.parquet: date/state/stock_a/ab/b/o):
  small multi-line chart of stock levels by blood type for a selected state.
- Organ pledges (organ_01_timeseries.parquet: date/state/daily/daily_7dma):
  cumulative pledge line since 2009, state filter.
- PeKa B40 screenings (pekab40_01_timeseries.parquet: date/state/daily):
  trend chart of daily screenings by state.
- All charts follow the design system. Handle the 2019-2026 range gracefully.
- Add "Data: MoH KKMNOW (GitHub)" attribution in the section footer.

---

## User-friendliness
- Mobile-readable (stack cards, horizontal-scroll tables as fallback).
- Meaningful empty/error states: friendly message + retry button, never raw JSON.
- Rate-limit awareness ("refreshing… done" status line).
- Loading = skeletons, not spinners-in-empty-space.
- Footer: "Data: Malaysian Government Open API" + link to developer.data.gov.my.
- Accessibility: contrast ≥ WCAG AA, focus-visible outlines, aria-labels on
  icon buttons, prefers-reduced-motion respected. Skip link, keyboard-operable
  sortable table headers, aria-current on active nav, aria-sort on sorted
  columns, aria-live region for location changes, "View data table"
  alternative for every chart.
- Offline state communicated clearly (header badge when SW reports offline).

---

## Security checklist (verify before finishing — no exceptions)
- CSP: strict Content-Security-Policy with NO 'unsafe-eval' and NO wildcard
  connect-src. Allowlist exactly: self, api.data.gov.my,
  raw.githubusercontent.com (MoH parquet), the OSM tile server, and the
  Worker's own /api/*. Nominatim ONLY via the Worker proxy — never in-browser.
  'unsafe-inline' allowed ONLY for the single authored <script>/<style> in
  index.html — no third-party inline scripts.
- No secrets in client code: no API keys, tokens, or URLs-with-embedded-creds
  anywhere in public/. This app needs none — verify that holds.
- Subresource Integrity (SRI): every external/vendor script and stylesheet
  pinned with integrity= hashes (Chart.js, Leaflet, hyparquet).
- XSS hygiene: any API field rendered into HTML (weather text, station names,
  GTFS stop names, MoH strings) goes through textContent or an escape function
  — never innerHTML with raw data. Hunt for all render sites during review.
- Headers (via public/_headers + Worker): CSP, HSTS (max-age ≥ 31536000,
  includeSubDomains), X-Content-Type-Options: nosniff, X-Frame-Options: DENY,
  Referrer-Policy: strict-origin-when-cross-origin, restrictive
  Permissions-Policy allowing ONLY geolocation.
- Service worker: never cache opaque/cross-origin responses; cache version
  bumped on any loader contract change; scope limited to site root.
- Rate-limit safety: token bucket per API family enforced client-side; no
  polling loops; manual refresh only.
- PWA scope: manifest start_url "/", no external URLs inside manifest; icons
  served same-origin.
- Third-party surface: document every external host the page connects to in
  the final summary (should be ≤ 4-5: gov API, MoH GitHub, OSM tiles, the
  Worker's /api/*, plus self).
- Final pass: open DevTools → Network and confirm zero requests to unexpected
  hosts; run Lighthouse security category if available; state in the summary
  exactly which external hosts the page talks to.

---

## API gotchas (verified — respect these)
- Trailing slash REQUIRED on data.gov.my paths (301 otherwise; every request
  costs rate-limit budget).
- Rate limit: 4 requests/min per family (weather, data-catalogue, opendosm,
  gtfs-static, gtfs-realtime). Never two same-family calls within 3s. Rolling
  token bucket client-side. Memory + localStorage cache 15 min. Manual refresh
  only — never poll.
- fuelprice and exchangerates default to OLDEST first — always sort=-date.
- Unknown dataset ids → 404 {"status_code":404,...} — check before wiring UI.
- GTFS static upstream 302-redirects to an S3 bucket (CORS-fragile) — the
  /api/gtfs Worker route does the hop server-side with 6h edge cache.

---

## Process
1. Explore the live APIs via the mygov MCP tools and verify every response
   shape you'll consume.
2. Restructure the HTML with clean semantic layout + design-system CSS variables.
3. Add the PWA layer (manifest, icons, service worker, registration).
4. Apply the theme section by section (charts, tables, cards, weather).
5. Keep everything as plain files in public/ — static-only, Cloudflare-ready.
6. Run the security checklist (Network tab pass, CSP, XSS hunt, SRI).
7. Before finishing, open locally and sanity-check: mobile width, dark theme
   contrast, chart legibility, PWA installability, offline behavior, and that
   every section renders real data from the mygov tools.

Finish with a short summary of the design decisions you made.
