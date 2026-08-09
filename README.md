# mygov

A dashboard for Malaysia's Government Open API — weather, fuel prices, economic
statistics and public transport, in one page.

**Live:** https://mygov.faizalmzain.com

No build step, no framework, no npm dependencies at runtime. The whole app is a
single HTML file plus a service worker, served by a Cloudflare Worker that also
proxies the reverse-geocoding and GTFS archive calls.

---

## What it shows

| Section | Source | Contents |
| --- | --- | --- |
| Weather | MET Malaysia | 7-day forecast for all 360 locations, severe-weather warnings, recent earthquakes |
| Fuel & Households | Ministry of Finance | Weekly RON95 / RON97 / diesel ceiling prices, household income |
| Economy | DOSM (OpenDOSM), EPF | Headline vs core CPI by expenditure division, year-on-year inflation by state, unemployment, quarterly real GDP, latest EPF dividend |
| Finance | Bank Negara Malaysia, PayNet | Exchange rates vs key currencies (daily or monthly), interest rates by bank type, daily FPX payment value and volume |
| Vehicles & Ridership | JPJ, KTMB | Monthly new-vehicle registrations stacked by fuel type (the EV adoption curve), daily KTMB ridership per service |
| Population | DOSM (OpenDOSM) | National population 1970-present, ethnic composition |
| Health | Ministry of Health | Daily blood donations with blood-type split, organ pledges, PeKa B40 screenings |
| Postcodes | Pos Malaysia | Searchable postcode → city → state reference |
| Transport | KTMB, Prasarana, Malaysia Airports | GTFS schedules — route/stop search, nearest stops, busiest routes, LRT/MRT metro line diagram; live arrivals & departures board for 13 airports (FIDS) |
| Live | KTMB, Prasarana | GTFS-Realtime vehicle positions on a live map, with "last seen" cards |
| Trend Radar | News + Sebenarnya.my | Top-10 hot issues in Malaysia, clustered daily by Gemini, with Sebenarnya fact-check status |

---

## Trend Radar (hot issues)

A daily scoop of Malaysia's hot issues and trends, fed by:

- **News RSS**: MalayMail, Free Malaysia Today, Utusan
- **Fact-check feed**: Sebenarnya.my (MCMC) — used to verify/debunk circulating claims

The collector clusters ~100 raw signals into a ranked top-10 issue list (BM titles,
categories, cross-source counts) using the **Gemini API** (`gemini-flash-latest`),
then writes `public/radar.json`. Each issue carries a fact-check status
(`verified_claim` / `debunked` / `no_check_found`) matched deterministically
against Sebenarnya posts, plus clickable source URLs.

### Pipeline

```
GitHub Actions (collect_radar.yml)     Hermes cron (digest, 10 PM MYT)
  daily 9 AM MYT (or manual dispatch)      reads live radar.json
  python3 tools/collect_radar.py            sends top-5 to Telegram
  GOOGLE_API_KEY secret → Gemini cluster    (no collecting — read-only)
  commit + push radar.json
  Cloudflare auto-deploy → mygov.faizalmzain.com/radar.json
```

- **Collector:** `tools/collect_radar.py` — RSS fetch, Gemini clustering with
  JSON-rescue parsing, deterministic Sebenarnya fact-check matching, URL
  backfill. Falls back to keyword clustering if the Gemini call fails (never
  crashes).
- **Repo secret required:** `GOOGLE_API_KEY` (Gemini API key) — without it the
  collector degrades to keyword clustering in CI.
- **Workflow:** `.github/workflows/collect_radar.yml` — scheduled 01:00 UTC
  (9 AM MYT) + manual `workflow_dispatch`, commits as `github-actions[bot]`
  with `contents: write`.
- The dashboard fetches `/radar.json` (same-origin) and renders issue cards.

---

## KKM health data (daily collector)

The Health section (blood donations, organ pledges, PeKa B40) updates daily,
and every visitor used to spend **3 of the 4-per-minute `data-catalogue`
budget** fetching it. It is now pre-collected by a GitHub Action, mirroring
the Trend Radar pipeline:

- **Collector:** `tools/collect_health.py` — fetches the three MoH catalogue
  series (`blood_donations` windowed to 3 years, `organ_pledges`,
  `pekab40_screenings`) and writes `public/health.json` in the same compact
  `{t0, n, keys, series}` shape the app's `denseDaily()` builds in the
  browser (82 KB instead of ~700 KB of raw rows).
- **Workflow:** `.github/workflows/collect_health.yml` — daily 00:30 UTC
  (8:30 AM MYT) + manual `workflow_dispatch`, syntax-guarded, commits as
  `github-actions[bot]` with `contents: write`.
- The dashboard fetches `health.json` (same-origin) and only falls back to
  the live API when the file is missing or more than ~6 days old (e.g. on
  plain static hosting without the Action).

---

## Architecture

```
public/
  index.html            entire app — markup, design system, logic
  sw.js                 service worker (offline shell + API fallback)
  manifest.webmanifest  PWA manifest
  icons/                generated PNGs (192, 512, apple-touch)
  vendor/               self-hosted Chart.js, Leaflet (SRI-pinned)
src/
  index.js              Worker: static assets + /api/reverse, /api/gtfs, /api/fids
tools/
  make-icons.mjs        regenerates the icons (no image dependencies)
  collect_radar.py      Trend Radar collector (see above)
wrangler.jsonc
```

The Worker serves `public/` through the `ASSETS` binding and owns three routes,
`/api/reverse`, `/api/gtfs` and `/api/fids`. Everything else is static.

> Static assets are served by Cloudflare's asset router **without invoking the
> Worker**, so response headers for them come from `public/_headers`, not from
> `src/index.js`.

### Why there is a Worker at all

The weather section can centre itself on wherever you are, which needs
reverse geocoding. That call cannot be made from the browser:

1. `nominatim.openstreetmap.org` returns **no `access-control-allow-origin`
   header**, so a direct browser request is blocked by CORS.
2. Nominatim's usage policy requires a descriptive `User-Agent`. Browsers
   forbid scripts from setting that header, so only a server-side call can
   comply.

`/api/reverse` does the call server-side with a proper User-Agent, rounds
coordinates to ~1 km before forwarding (so nearby visitors share a cache entry
and precise locations are never stored), and caches results at the edge for a
day. If the proxy is unavailable the UI degrades to a manual location search
rather than breaking.

The second route, `/api/gtfs`, exists for a different reason. Upstream
`/gtfs-static/*` answers **302 to an S3 bucket**, so the browser has to pass
CORS on the *redirect target*. That is fragile — any network layer that
intercepts that hop surfaces it as an opaque CORS failure the page cannot
distinguish from being offline. Doing the hop server-side removes the
cross-origin redirect entirely and lets the ZIP be edge-cached for 6 hours, so
the government API sees a handful of requests a day rather than one 8 MB
download per visitor. The client still falls back to fetching the API directly
if the proxy is absent, so the page works on plain static hosting too.

The third route, `/api/fids`, backs the live flight board. Malaysia Airports'
FIDS endpoint (`api.myairports.com.my`) requires an `x-api-key` header and
answers without CORS headers, so browsers cannot call it directly. The Worker
injects the key (from the `FIDS_API_KEY` variable), adds
`Access-Control-Allow-Origin: *`, slims the response to the fields the board
renders, and edge-caches it for 60 seconds so the airport API sees one request
per minute per board, not one per visitor.

### Security

- **CSP** with no `'unsafe-eval'`, `object-src 'none'`, `frame-ancestors
  'none'`, and a `connect-src` allowlist, plus HSTS, `nosniff`,
  `X-Frame-Options`, a restrictive `Permissions-Policy` (only `geolocation`,
  same-origin) and `strict-origin-when-cross-origin` referrer policy. All in
  `public/_headers`.
- **Chart.js and Leaflet are pinned and SRI-checked**
  (`integrity="sha384-…"`), so altered bytes are refused rather than executed.
- Both API routes **validate input against a strict allowlist** and never
  interpolate user input into an upstream URL, and they reject cross-origin
  callers — they exist for this page, not as a public proxy.
- No secrets, tokens or account identifiers are in the repo; the app needs
  none. `.dev.vars` and `.wrangler/` are gitignored.
- No analytics. The page connects to exactly three hosts: itself (static assets
  and `/api/*`), `api.data.gov.my` (every dataset, health included) and
  `tile.openstreetmap.org` (map tiles in the Live section). Every library is self-hosted. The "Buy me a coffee" button is a
  plain link, not their tracking widget. Earthquake and live-vehicle cards
  include an outbound Google Maps link — a normal link the reader chooses to
  follow, not a request the page makes.

---

## Working with the API

Notes that cost time to discover — all verified against live responses.

**A trailing slash is required.** `GET /weather/forecast?limit=1` responds
`301` to `/weather/forecast/?limit=1`. Every URL the app builds ends in `/`, so
no request wastes a redirect hop against the rate limit.

**Rate limit: 4 requests per minute, per API family** (`weather`,
`data-catalogue`, `opendosm`, `gtfs-static`, `gtfs-realtime`). The app:

- fetches each family once per session, strictly sequentially, ~1.2 s apart;
- never lets two calls to the *same* family land within 3 s — bursts trip the
  limiter even when the per-minute count is legal;
- enforces a rolling 4-per-60 s token bucket per family;
- caches results in memory + `localStorage` for 15 minutes;
- never polls. Refresh is manual.

Total cold load: **11 requests** — weather 3, catalogue 2, opendosm 4,
gtfs-static 2, gtfs-realtime 2 — plus the health section's static
`health.json` (same-origin, produced by the daily KKM collector, no API
budget spent). GitHub is not called at all. Only weather + fuel (5 requests)
are fetched on first paint; economy, finance, population, health, postcodes,
transport and live are lazy-loaded as their sections scroll into view, so the
first screen renders before the slowest datasets arrive.

**Dataset ids that exist** (many plausible ones do not — an unknown id returns
`404` with `{"status_code":404,...}`):

- `data-catalogue`: `fuelprice`, `hh_income`, `exchangerates`,
  `interestrates`, `poskod` — plus `arrivals`, `passports`, `births` and
  `mnha`, which exist but are frozen (see *Data freshness* below), and
  `blood_donations`, `organ_pledges`, `pekab40_screenings`, which the KKM
  collector uses (see above)
- `opendosm`: `cpi_core`, `cpi_headline`, `lfs_month`, `gdp_qtr_real`,
  `population_malaysia`
- Not found: `electrictariff`, `watertariff`, `interestrate`, `unemployment`,
  `cpi_2d`, `opr`

**Gotchas in the catalogue datasets** (all verified against live responses):

- `interestrates` has **no `opr` series** — the rate codes are lending and
  deposit rates (`br`, `alr`, `sr`, `fdr_*`, `wabr`…). The Finance section
  charts the commercial base rate (`bank=commercial, rate=br`) instead, which
  tracks the OPR, and says so in the UI.
- `exchangerates` publishes each month five times (`start`/`low`/`high`/`avg`/
  `end`); filter to `indicator=avg` for a single monthly series.
- `poskod` has no `date` column, so `sort=-date` fails on it (columns are
  `city`, `state`, `postcode`).
- `population_malaysia` is published in **thousands of people**, one row per
  year × sex × ethnicity × age band. Only one `filter` is allowed per request,
  so narrow to `filter=overall@age` (which drops ~95% of the rows) and split
  by sex and ethnicity in the browser.

**Date-range filters** use `<YYYY-MM-DD>@<date_column>` syntax, e.g.
`?id=fuelprice&date_start=2021-01-01@date`.

**Server-side filtering works** and is worth using:
`?id=fuelprice&filter=level@series_type` returns only the price levels,
halving the payload. Without it you also get `change_weekly` delta rows
interleaved on the same dates — charting the raw response draws a sawtooth
through zero.

**Locations are keyed by `location_id`, not name.** The forecast feed has 360
distinct ids but only ~284 distinct names: "Perlis" exists as a state
(`St001`), a district (`Ds002`) and a town (`Tn001`), each with its own
forecast. Keying by name silently merges them. Prefixes are `St` state,
`Ds` district, `Tn` town, `Dv` division, `Rc` recreation.

**MET free text arrives with HTML entities already encoded** (`&amp;`), so it
must be decoded before escaping or readers see the raw entity. The warnings
endpoint also carries "No Advisory" all-clear notices with `null` validity
dates — `new Date(null)` is the epoch, which renders a bogus
"valid 01 Jan 1970". Both are handled.

**GTFS static** ships as ZIP. `routes.txt` column *order* differs between
agencies, so CSV is parsed by header name. For the bus feeds only
`routes`/`trips`/`stops`/`agency` are inflated — Prasarana's `stop_times.txt`
alone is 5.6 MB of the 8.8 MB archive and is never decompressed. The rail feed
(`gtfs_rapid_rail_kl.zip`) is the exception: its `stop_times.txt` is small
enough to read, which is how the LRT/MRT metro diagram gets the ordered
station sequence per line. It also carries the official route colors
(`route_color`) used to draw each line.

The rail feed is served by the same `/gtfs-static/prasarana` endpoint with
`category=rapid-rail-kl` — 187 stations across 8 lines (Ampang, Sri Petaling,
Kelana Jaya, Shah Alam, MRT Kajang, MRT Putrajaya, Monorail, BRT Sunway).

**GTFS realtime** legitimately returns zero vehicles outside service hours.
That is an empty state, not an error — the UI says so and shows the feed's own
timestamp as proof it responded.

---

## No-dependency implementations

Three things that would normally pull in a library:

- **ZIP reading** — a central-directory reader using the platform's
  `DecompressionStream('deflate-raw')`. No JSZip.
- **GTFS-Realtime protobuf** — a ~90-line wire-format reader (varint /
  length-delimited / fixed32) covering just the `VehiclePosition` subset.
  No protobufjs, no `.proto` file.
- **Icons** — `tools/make-icons.mjs` renders the PNGs with a hand-written
  encoder (`zlib` + CRC32), supersampled 4× for clean edges.

Chart.js and Leaflet are the only runtime dependencies. They live in
`public/vendor/` (self-hosted with subresource integrity, so there is no CDN
to go down and the app works fully offline) and are precached by the service
worker.

### Compacting daily series

Several datasets are one JSON object per category per day — blood donations
alone are five keys over three years. `denseDaily()` collapses each key to a
start day plus a flat array of values, which is roughly a fifth the size and
keeps these sections inside the localStorage budget the other eight share.
Seven-day moving averages are computed at render time rather than cached, for
the same reason.

## Preferences

All preferences are stored in `localStorage` only — nothing leaves the device:

- **Theme** — dark, light, or follow the system, plus a persisted choice.
- **Text size** — a large-text mode for readability.
- **Language** — English or Bahasa Melayu for the interface. Weather warnings
  use the API's native `_bm` fields when available, and Malay forecast phrases
  are mapped to English when the interface language is English.

The live maps use OpenStreetMap tiles (© OpenStreetMap contributors), with a
CSS filter to keep them dark in dark mode. The `img-src` CSP allows
`tile.openstreetmap.org` for exactly that purpose.

---

## Caching

Two layers, deliberately different:

- **App (`localStorage`, 15 min TTL)** — drives freshness. Holds compacted view
  models, not raw responses: forecast strings are dictionary-compressed, and
  GTFS is reduced to counts plus stop coordinates before storage. A full cold
  load is a few hundred KB, well under quota, and `cacheSet` degrades to
  memory-only if the quota is hit anyway.
- **Service worker** — drives offline. Cache-first for the shell;
  API responses are cached on success and served only when the network fails.

The service worker deliberately does **not** use stale-while-revalidate for
`api.data.gov.my`. SWR fires a background revalidation on every cache hit,
which would silently double request volume against a 4/min limit and push the
app into `429`. The app's 15-minute TTL is the "revalidate" half, moved into a
rate-limit-aware layer.

> **When changing a loader's return shape, bump `CK`** (the
> `mygov.cache.vN.` prefix) in `index.html`. Otherwise a visitor's
> 15-minute-old cache is replayed into a renderer that expects different
> fields. Old prefixes are purged automatically on load.

---

## Local development

```bash
npx wrangler dev
```

Serves on http://localhost:8788 with `/api/reverse`, `/api/gtfs` and
`/api/fids` all working locally — `wrangler dev` picks up the `FIDS_API_KEY`
variable declared in `wrangler.jsonc` automatically.

Regenerate icons after changing the palette:

```bash
node tools/make-icons.mjs
```

---

## Deploying

The site deploys automatically: this GitHub repo is connected to the
`mygov` Worker via Cloudflare's **Workers Git integration** (Workers & Pages →
mygov → Settings → Builds & Deployments). Every push to `main` triggers a new
production deploy — no workflow file, secrets, or manual steps required.

For manual deploys (e.g. testing a branch before pushing):

```bash
npx wrangler deploy
```

The custom domain is attached in the Cloudflare dashboard under
**Workers & Pages → mygov → Settings → Domains & Routes**, which creates the
`mygov` CNAME on `faizalmzain.com` automatically. No secrets are required; the
only variable is `FIDS_API_KEY` (a public key, declared as a `var` in
`wrangler.jsonc` so `wrangler deploy` pushes it with the code).

---

## Data freshness

A dataset earns its place by being **current**, not by being long. Deep history
is welcome — a 1970-2026 population series is more useful than a short one —
but a series whose *last* update is years old has nothing to compare against,
and charting it invites readers to mistake stale numbers for today's.

So: the pill in each section header shows **"data as of &lt;date&gt;"** — the
newest row that section actually renders, not when we fetched it — and appends
**"⚠️ may be delayed"** once that date is more than 183 days old. The date
comes from `LOADERS[id].asOf(data)`; a section that returns nothing (a static
lookup, a live feed) keeps the old "updated HH:MM" fetch time instead.

Datasets that had stopped updating entirely were removed rather than captioned:

| Removed | Last update |
| --- | --- |
| `arrivals`, `passports` (the whole Tourism section) | 2024-10-01 |
| `births` | 2023-07-31 |
| `mnha` (national health accounts) | 2022-01-01 |
| `population_state` | 2023-01-01 |

`poskod` is exempt: it is a static reference table, not a time series, so it
has no publication date that can go stale. It defines no `asOf`, so its pill
keeps showing the fetch time.

---

## Adding a dataset

**Into an existing section** — add one request to the relevant loader in
`index.html`, reduce it to a compact array, and render it. Mind the 4/min cap:
`opendosm` is at 4 of 4 (economy 3 + population 1), so a new OpenDOSM series
must share an existing call or wait out a minute. `data-catalogue` has 2 in use
(fuel + finance); health moved off the API to a daily static file.

```js
const x = await request("data-catalogue", "/data-catalogue", { id: "YOUR_ID" });
```

**As a new section** — two registrations, and the rest is automatic:

```js
SECTIONS.push({ id:"myid", label:"My Data", icon:"🧭", family:"data-catalogue" })
META.myid    = { title, desc, how, eps:[...] }
LOADERS.myid = { load, render, after, asOf }
// after(data) feeds the top KPI row.
// asOf(data)  returns the newest data date the section renders, for the
//             "data as of …" pill. Omit it and the pill shows the fetch time.
```

Nav entry, scroll-spy, skeleton, error/retry, caching and throttling are all
wired from those (new sections load eagerly; `LAZY` in `index.html` marks the
scroll-triggered ones). Browse available ids at
[developer.data.gov.my](https://developer.data.gov.my).

---

## Accessibility

Skip link, `:focus-visible` outlines throughout, `aria-label`s on icon-only
controls, keyboard-operable sortable table headers (`Enter`/`Space`),
`aria-current` on the active nav item, `aria-sort` on sorted columns, and
real `<button>`s for selectable weather rows with an `aria-live` region
announcing location changes. `prefers-reduced-motion` is honoured — it disables
chart animations, the KPI count-up and smooth scrolling. Every chart has a
"View data table" alternative for users who can't use tooltips. Body text is
`#e8ecf4` on `#0a0c10` (~16:1 contrast); the dimmest supporting text stays
above 4.5:1 in both themes.

---

## Licence & attribution

Code: MIT. Data © Government of Malaysia, via the
[Open API](https://developer.data.gov.my) — MET Malaysia, MOF, DOSM, KTMB and
Prasarana. Reverse geocoding © OpenStreetMap contributors (ODbL).
