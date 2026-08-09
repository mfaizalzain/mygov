# mygov

A dashboard for Malaysia's Government Open API — weather, fuel prices, economic
statistics and public transport, in one page.

**Live:** https://mygov.faizalmzain.com

No build step, no framework, no npm dependencies at runtime. The whole app is a
single HTML file plus a service worker, served by a Cloudflare Worker that also
proxies one geocoding call.

---

## What it shows

| Section | Source | Contents |
| --- | --- | --- |
| Weather | MET Malaysia | 7-day forecast for all 360 locations, severe-weather warnings, recent earthquakes |
| Fuel & Households | Ministry of Finance | Weekly RON95 / RON97 / diesel ceiling prices, household income |
| Economy | DOSM (OpenDOSM) | Core CPI by expenditure division, unemployment, quarterly real GDP |
| Transport | KTMB, Prasarana | GTFS schedules — route and stop search, nearest stops, busiest routes |
| Live | KTMB, Prasarana | GTFS-Realtime vehicle positions on a live map, with "last seen" cards |

---

## Architecture

```
public/
  index.html            entire app — markup, design system, logic
  sw.js                 service worker (offline shell + API fallback)
  manifest.webmanifest  PWA manifest
  icons/                generated PNGs (192, 512, apple-touch)
src/
  index.js              Worker: static assets + /api/reverse
tools/
  make-icons.mjs        regenerates the icons (no image dependencies)
wrangler.jsonc
```

The Worker serves `public/` through the `ASSETS` binding and owns two routes,
`/api/reverse` and `/api/gtfs`. Everything else is static.

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

### Security

- **CSP** with no `'unsafe-eval'`, `object-src 'none'`, `frame-ancestors
  'none'`, and a `connect-src` allowlist, plus HSTS, `nosniff`,
  `X-Frame-Options`, a restrictive `Permissions-Policy` (only `geolocation`,
  same-origin) and `strict-origin-when-cross-origin` referrer policy. All in
  `public/_headers`.
- **Chart.js is pinned and SRI-checked** (`integrity="sha384-…"`), so altered
  CDN bytes are refused rather than executed.
- Both API routes **validate input against a strict allowlist** and never
  interpolate user input into an upstream URL, and they reject cross-origin
  callers — they exist for this page, not as a public proxy.
- No secrets, tokens or account identifiers are in the repo; the app needs
  none. `.dev.vars` and `.wrangler/` are gitignored.
- No analytics, no third-party requests beyond the pinned Chart.js. The
  "Buy me a coffee" button is a plain link, not their tracking widget.

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

Total cold load: **14 requests** — weather 3, catalogue 2, opendosm 3,
gtfs-static 2, gtfs-realtime 2. Only weather + fuel (5 requests) are fetched
on first paint; economy, transport and live are lazy-loaded as their sections
scroll into view, so the first screen renders before the slowest datasets
arrive.

**Dataset ids that exist** (many plausible ones do not — an unknown id returns
`404` with `{"status_code":404,...}`):

- `data-catalogue`: `fuelprice`, `hh_income`, `population_malaysia`
- `opendosm`: `cpi_core`, `cpi_headline`, `lfs_month`, `gdp_qtr_real`
- Not found: `electrictariff`, `watertariff`, `interestrate`, `unemployment`, `cpi_2d`

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
agencies, so CSV is parsed by header name. Only `routes`/`trips`/`stops`/
`agency` are inflated — Prasarana's `stop_times.txt` alone is 5.6 MB of the
8.8 MB archive and is never decompressed.

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

Chart.js and Leaflet are the only runtime dependencies, loaded from a CDN with
subresource integrity and precached by the service worker.

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
  GTFS is reduced to counts before storage. A full cold load is ~200 KB, well
  under quota, and `cacheSet` degrades to memory-only if the quota is hit
  anyway.
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

Serves on http://localhost:8788 with the `/api/reverse` route working locally.

Regenerate icons after changing the palette:

```bash
node tools/make-icons.mjs
```

---

## Deploying

```bash
npx wrangler deploy
```

The custom domain is attached in the Cloudflare dashboard under
**Workers & Pages → mygov → Settings → Domains & Routes**, which creates the
`mygov` CNAME on `faizalmzain.com` automatically. No environment variables or
secrets are required.

---

## Adding a dataset

**Into an existing section** — add one request to the relevant loader in
`index.html`, reduce it to a compact array, and render it. Mind the 4/min cap:
`opendosm` already uses 3 of its 4 slots.

```js
const x = await request("data-catalogue", "/data-catalogue", { id: "YOUR_ID" });
```

**As a new section** — two registrations, and the rest is automatic:

```js
SECTIONS.push({ id:"myid", label:"My Data", icon:"🧭", family:"data-catalogue" })
META.myid    = { title, desc, eps:[...] }
LOADERS.myid = { load, render, after }   // after() feeds the top KPI row
```

Nav entry, scroll-spy, skeleton, error/retry, caching and throttling are all
wired from those. Browse available ids at
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
