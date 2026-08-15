# mygov

A dashboard for Malaysia's Government Open API - weather, fuel prices, economic
statistics and public transport, in one page.

**Production:** https://malaysia-at-a-glance.com  

No build step, no framework, no npm dependencies at runtime. The whole app is
plain HTML + CSS + JS (index.html, styles.css, app.js) plus a service worker,
served by a Cloudflare Worker that also
proxies the reverse-geocoding, GTFS archive, flight-board, live-bus, flood,
service-alert and air-quality calls.

## AI agents: MCP connector & OpenAPI Proxy

The same data is available to AI coding agents through an official MCP plugin -
**[mfaizalzain/mygov-mcp](https://github.com/mfaizalzain/mygov-mcp)** - exposing
weather, fuel prices, CPI/OpenDOSM, GTFS transit, live Rapid bus positions, flood
risk, groceries, monthly tourism arrivals, the latest Rapid KL service alert and
live air quality as **twelve read-only tools**.
Published for Claude Code (`@claude-community` marketplace) and Codex/ChatGPT
(universal plugin directory). Also supports Server-Sent Events (SSE) and OpenAPI
proxy routing for custom connected agents and Gemini workflows. No API key,
same rate-limit rules as the app.

---

## What it shows

| Section | Source | Contents |
| --- | --- | --- |
| Warnings & Hazards | MET Malaysia, JPS, Prasarana (myRapid), Open-Meteo | Everything currently on issue, as a **status strip** of three tiles. The first merges severe-weather warnings, **earthquakes within 500 km of Malaysia in the last 7 days** from **MET Malaysia and USGS** (only the last 24 hours count towards the section's active-alert badge; MET's rows are filtered on its own `n_distancemas` field, USGS rows on distance to the nearest of 13 coastal anchors, and the same rupture reported by both is collapsed), flood-risk stations, the **latest Rapid KL service alert** and **live air quality** into **one alert carousel** (filter chips: all / weather / earthquakes / my area / marine; Rapid + AQI ride under All Malaysia only). The second is water-level stations at danger / warning / alert from JPS telemetry with status map. The third is air quality for **18 major cities as comparison cards** (Open-Meteo US AQI & PM2.5, sorted worst-first with multi-tier resilient fallback). Live only - nothing here is historical |
| Weather | MET Malaysia, Open-Meteo | Unified Weather Station: live current conditions at your location with interactive mini-map & live condition pin badge (temperature, feels-like, humidity, wind), a **24-hour hourly forecast timeline** (hour, condition icon, temperature, rain probability % with color pills), a dynamic **7-day daily forecast outlook** (daily high/low temperature range, rain probability, conditions), instant location search with auto-complete suggestions & popular Malaysian hubs, and a collapsed-by-default **360-location table** from MET Malaysia |
| Household | Ministry of Finance, KPDN | Weekly RON95 / RON97 / diesel ceiling prices, household income, and the PriceCatcher groceries basket (a merged **Groceries sub-block** with per-district price levels) |
| Economy | DOSM (OpenDOSM), EPF | Headline vs core CPI by expenditure division, year-on-year inflation by state, unemployment, quarterly real GDP, latest EPF dividend |
| Finance | Bank Negara Malaysia, PayNet | Exchange rates vs key currencies (daily or monthly), interest rates by bank type, daily FPX payment value and volume |
| Vehicles & Ridership | JPJ, KTMB | Monthly new-vehicle registrations stacked by fuel type (the EV adoption curve), and a **Car sales** sub-block - YTD registrations, top makers, **top EV makers** and EV share from JPJ's granular registration data |
| People | DOSM (OpenDOSM + storage) | National population 1970-present and ethnic composition, then the same estimates by state, district and constituency (a merged **Places explorer** with a Malaysia-wide default chip, **paginated tables** and **federal territories shown by constituency** - KL/Putrajaya/Labuan have no districts) - per-district ethnicity, sex split, age structure, median income, poverty and inequality, and per-seat income, poverty, gini and unemployment. A merged **Election Results** sub-block adds the latest SPR results per category - PRU-15 parliamentary and the latest state election for **every state** (10 from the pru-dun dropdown, Perlis/Perak/Pahang embedded in PRU-15) plus the latest by-election - with winner, votes, majority and party-colour bars, **paginated at 20 seats**, **segregated by state** and **searchable** (constituency, winner or party) |
| Tourism (sub-block of Economy) | Tourism Malaysia | Monthly international visitor arrivals by country of nationality (top 51) - the month's total, month-on-month and year-on-year growth vs 2025 and 2019, plus year-to-date, from Tourism Malaysia's published PDFs. A merged **Hotels sub-block** shows quarterly **hotel performance by state** from the Paid Accommodation Survey - occupancy rate, average room rate and hotel guests (domestic/international split) for all 16 states, current quarter vs a year earlier |
| Health (sub-block of People) | Ministry of Health | Daily blood donations with blood-type split, organ pledges, PeKa B40 screenings |
| Postcodes | Pos Malaysia | Searchable postcode → city → state reference |
| Transport | KTMB, Prasarana, Malaysia Airports | GTFS schedules - route/stop search, nearest stops, busiest routes, LRT/MRT metro line diagram; live arrivals & departures board for 13 airports (FIDS) |
| Live (sub-block of Public Transport) | KTMB, Prasarana | KTMB GTFS-Realtime trains + **800+ live Rapid KL buses from Prasarana's official kiosk feed** on a clustered live map, with route chips (click to filter) and tooltips |
| Trend Radar | News (Bernama, Malay Mail, FMT, Utusan, Astro Awani) + Sebenarnya.my | Dual-mode intelligence carousel: **🔥 Viral & Fact-Checks** (Top-10 hot issues clustered daily by Gemini with Sebenarnya fact-check status & claim verification) and **⚡ Breaking News** (live multi-agency breaking news wire with category filters and article reading modals) |
| Forecasts | Derived | 14-day projections on the daily count series that measurably beat a naive guess, drawn as a dashed extension with an 80% band |
| Travel Outlook (hero band) | mycal holiday + KPM school calendars, Gemini | the next 8 weeks of peak travel periods - school breaks, public holidays and long weekends with impact badges and a one-line English outlook each, plus tips to travel around them, with the next-holiday and school-session chips riding under the band |

---

## Festive themes

The dashboard carries a low-key seasonal layer that appears for everyone
nationwide. It changes only the accent tokens, a soft body glow, and a band of
small header motifs along the right edge; the layout and data presentation stay
unchanged. Dark and light themes, the user's reduced-motion preference, and the
visitor's theme toggle are all respected.

| Season | Window | Header motif |
| --- | --- | --- |
| Kaamatan | 25-31 May | Padi stalk in grain |
| Hari Gawai | 1-4 June | Kenyalang (hornbill) |
| Merdeka / Malaysia Day | 1 August-16 September | Waving Jalur Gemilang |
| Hari Raya | 7 days before / 7 days after | Ketupat, with its plait |
| Chinese New Year | 7 days before / 3 days after | Lantern |
| Deepavali | 7 days before / 3 days after | Diya |
| Christmas | 20-27 December | Tiered tree |

The motifs tile at roughly 112x74 and drift sideways by exactly one tile width,
which loops seamlessly under `repeat-x`. They were previously drawn one per
header at 360x360 and offset to -140px, which showed only a 70px slice through
the middle of each glyph, and each SVG carried its own `opacity=".5"` on top of
the layer's `.10` - an effective alpha near 0.05. The layer was shipping
invisible; opacity is now applied once, in CSS.

Merdeka is the one season drawn from a real object rather than a symbol, so it
gets a full Jalur Gemilang - 14 alternating stripes, the canton over the upper
eight, the crescent and the fourteen-pointed Bintang Persekutuan - cropped past
the top-right corner of the header and waved with a travelling fold gradient.
Its palette is the flag's own: royal blue as the canvas, royal yellow as the
accent, stripe red left to the body glow and the header wash. Red is
deliberately *not* the accent - the dashboard already spends red on danger
(flood stations at warning, debunked radar claims, every `.err` badge), and an
accent in the same hue would read as alarm on screens that are only showing
data.

Kaamatan and Gawai are both harvest festivals, so they are told apart by what
each region is known for rather than by the harvest itself: padi for Sabah, the
hornbill for Sarawak. Kaamatan's palette is a ripening lime and amber, which
also separates it from Raya's deep green - the two were previously identical
themes, byte for byte in light mode.

Movable holidays (Hari Raya, Chinese New Year and Deepavali) are resolved from
the public-holiday calendar already mirrored into `public/slow.json`; the
fixed-date seasons are calendar windows in `public/app.js`. The visual tokens
and animated header treatments live in `public/styles.css`.

---

## Trend Radar (hot issues & breaking news)

A dual-mode intelligence hub for Malaysia's hot issues, viral claims, and real-time breaking news, fed by:

- **News RSS Feeds**: Bernama (EN + BM), Astro Awani, Malay Mail, Free Malaysia Today, and Utusan Malaysia
- **Fact-Check Feed**: Sebenarnya.my (MCMC) - used to verify/debunk circulating viral claims
- **Google Trends Malaysia**: Real-time viral search signals

### Dual-Mode Carousel UI

Trend Radar provides a zero-clutter segmented switcher in its header band to toggle between two views without adding extra vertical layout sections:

1. **🔥 Viral & Fact-Checks**: Top 10 viral controversies and circulating rumors clustered daily by Gemini (`gemini-flash-latest`), paired with grounded web search fact-checks and Sebenarnya post matches (`verified_claim` / `misleading` / `debunked` / `no_check_found`). Includes claim quotes, official verdicts, detailed facts, and source links.
2. **⚡ Breaking News**: Live Malaysian breaking news wire featuring source badges (`BERNAMA`, `MALAY MAIL`, `FMT`, `UTUSAN`, `ASTRO AWANI`), relative timestamps (`15m ago`), auto-classified categories (`politik`, `ekonomi`, `jenayah`, `bencana`, `kesihatan`, `sukan`, `nasional`), and a reading modal with full summary and direct source link.

### Pipeline

```
GitHub Actions (collect_radar.yml)     Hermes cron (digest, 10 PM MYT)
  daily 9 AM MYT (or manual dispatch)      reads live radar.json
  python3 tools/collect_radar.py            sends top-5 to Telegram
  GOOGLE_API_KEY secret → Gemini cluster    (no collecting - read-only)
  commit + push radar.json
  Cloudflare auto-deploy → malaysia-at-a-glance.com/radar.json
```

- **Collector:** `tools/collect_radar.py` - RSS fetch across 6 major Malaysian news outlets, Gemini clustering with JSON-rescue parsing, grounded fact-checking, breaking news HTML cleaning/deduplication, and URL backfilling. Falls back to deterministic keyword clustering if the Gemini API call fails.
- **Repo secret required:** `GOOGLE_API_KEY` (Gemini API key) - without it the collector degrades to keyword clustering in CI.
- **Workflow:** `.github/workflows/collect_radar.yml` - scheduled 21:19 UTC (05:19 MYT the next morning) + manual `workflow_dispatch`, commits as `github-actions[bot]` with `contents: write`.
- The dashboard fetches `/radar.json` (same-origin) and dynamically updates carousel tracks, counters, and bilingual translations.

---

## Collectors: how the data gets here

Collectors pre-fetch everything that changes at most daily, so visitors
spend zero API budget on it. All run as GitHub Actions and produce a static
JSON the dashboard reads same-origin (served from the Cloudflare edge):

| Collector | Workflow | Writes | Contents |
| --- | --- | --- | --- |
| KKM health | `collect_health.yml`, daily 21:07 UTC (05:07 MYT next day) | `public/health.json` | blood donations (3y), organ pledges, PeKa B40 |
| Slow data | `collect_slow.yml`, 4x daily 01:35 / 04:35 / 09:35 / 12:35 UTC (just after each BNM reference rate: 09:35 / 12:35 / 17:35 / 20:35 MYT) | `public/slow.json` | fuel, finance (incl. payment instruments), mobility, economy (incl. FDI flows), population, public holidays |
| PriceCatcher | `collect_prices.yml`, daily 13:30 UTC | `public/prices.json` | grocery basket index, per-item prices, 166 districts |
| Places | `collect_geo.yml`, weekly Mon 14:00 UTC | `public/geo.json` | state/district population + composition (ethnicity, sex, age), 222 parliament + 600 DUN seats with income, poverty, gini, unemployment per seat; district-level median income, poverty and gini from the OpenAPI |
| Insights | `collect_insights.yml`, chained to `collect_radar.yml` completion (~21:25 UTC / 05:25 MYT) | `public/forecasts.json`, `public/insights.json` | 14-day forecasts for the series that pass a backtest, plus a bilingual daily briefing |
| Car sales | `collect_cars.yml`, monthly 6th 02:30 UTC | `public/cars.json` | JPJ granular registrations - YTD totals, monthly fuel mix + EV share, top makers **and top EV makers** (current + previous year) |
| Tourism | `collect_tourism.yml`, monthly 2nd 02:30 UTC | `public/tourism.json` | Tourism Malaysia visitor-arrivals PDF - top-51 table with month, y/y vs 2025 and 2019, YTD (May 2026 seeded) |
| Hotels | `collect_hotel.yml`, quarterly 3rd 02:30 UTC (Jan/Apr/Jul/Oct) | `public/hotel.json` | Paid Accommodation Survey infographic - occupancy rate (AOR), average room rate (ARR) and hotel guests (domestic/international) for all 16 states, current quarter vs a year earlier. Only the latest quarter is public on the portal, so the collector probes newest-first (same pattern as tourism) and the dashboard shows the current quarter only |
| Travel Outlook | `collect_travel.yml`, weekly Mon 01:30 UTC | `public/travel.json` | next 8 weeks of peak travel periods from the holiday + KPM school calendars - school breaks, public holidays, long weekends with impact levels and one English line each (Gemini, deterministic fallback) |
| Rapid KL alerts | `collect_rapid.yml`, every 10 min | `public/rapid_alerts.json` | the **latest** myRapid PULSE service alert (title, excerpt, link, MYT timestamp). The source is behind Incapsula (a JS-challenge WAF; its wp-json also returns 401 for anonymous reads), so the collector scrapes it through the **r.jina.ai reader proxy** - run from GitHub's IP pool because jina's free tier rate-limits Cloudflare Worker egress to null |
| Live hazards | `collect_hazards.yml`, every 10 min | `public/aqi.json`, `public/flood.json`, `public/alerts.json` | Open-Meteo air quality for 18 cities, JPS at-risk flood gauges, and the combined earthquake + flood summary (MET **and USGS** - see the earthquake note below). These were previously aggregated inside the Worker on every request; the scheduled collector keeps them KV-first with a live Worker fallback |
| Highway traffic | `collect_traffic.yml`, every 10 min | `public/traffic.json` | InfoTrafikGZ Telegram posts - the concessionaires' own highway reports (PLUS, KESAS, LDP, MEX, KL-Karak). Cleaned of channel boilerplate; the ticker shows only the last 2 hours |
| Urban traffic | `collect_tomtom_traffic.yml`, hourly 06:00-23:00 MYT | `public/traffic_incidents.json` | TomTom Traffic Incident Details v5 for **10 urban and destination regions** - the city streets the highway feed never mentions. Categories come from TomTom's published v5 taxonomy (a CI assert fails the run on any name outside it), one jam reported across adjacent segments and both directions is collapsed into one, closures and jams outrank roadworks, and each region is capped at 40 with two thirds of the slots held back from roadworks - they never expire and would otherwise crowd out everything live. ~53 KB |
| Election Results | `collect_election.yml`, manual | `public/election.json` | Latest election per category from SPR's MySPRSemak JSON API (CSRF token + UUID ids from the page, then per-seat POSTs): PRU-15 parliamentary (208 seats - SPR omits Kedah P.017 and the federal-territory seats), the latest state election for **all 13 states** (10 via the pru-dun dropdown, Perlis/Perak/Pahang embedded in PRU-15's DUN payload), and the latest by-election. ~810 requests, one-time per election; results never change once published |

> Each workflow uploads **only its own key** (`kv_upload.py push <key>`). An
> unfiltered push also re-uploads the git-committed copies of the files that
> run did *not* regenerate, clobbering fresher KV values from another
> collector.

- Every collector finishes with `tools/embed_seo.py`, which (a) injects the
  **current headline values** (fuel, USD/MYR, CPI, blood donations, top radar
  issues) into the `<noscript>` fallback of `index.html` between the
  `<!-- SEO:SNAP -->` markers, so crawlers that never run JS still see fresh
  numbers on first pass, and (b) writes `public/feed.xml`, an RSS 2.0 feed of
  the Trend Radar issues. Both are idempotent - they only rewrite when the
  content actually changes, so collector commits stay clean.

- `tools/collect_health.py` and `tools/collect_slow.py` fetch from the
  data.gov.my API with **4 attempts and 5s/10s/15s backoff** (a transient
  failure in unattended CI must not cost a whole day of freshness), then
  write the data in the exact compact shapes the browser loaders build
  (`{t0, n, keys, series}` etc. - ~630 KB for slow.json vs ~5 MB of raw rows).
- The loaders (`loadHealth`, `loadFuel`, `loadFinance`, `loadMobility`,
  `loadEconomy`, `loadPopulation`) **try the static file first** via
  `readSlow()`, and only fall back to the live API when the file is missing
  or more than ~6 days old (e.g. on plain static hosting without the Action).
- Net effect: a cold visit costs **3 API requests** (weather) plus the
  real-time feeds - everything else is static. `interestrates` is the one
  series currently stale *upstream* (last published 2025-12); the collector
  captures whatever the source publishes.

---

## PriceCatcher basket index

KPDN enumerators record the shelf price of ~340 grocery items at ~2,100
premises across all 177 districts, daily. `tools/collect_prices.py` turns that
into `public/prices.json` (~131 KB).

**It is not on the OpenAPI.** `pricecatcher` carries `exclude_openapi: true`,
so `api.data.gov.my/data-catalogue/?id=pricecatcher` answers `404`. It exists
only as monthly Parquet on `storage.data.gov.my` - ~2.5 MB and ~1.6 M rows
*per month*. Same for `lookup_item` / `lookup_premise`. The collector reads 13
months (~33 MB) and aggregates in CI, so the browser never sees any of it.
This is also why it is the one collector with dependencies (`pandas`,
`pyarrow`): no stdlib module reads Parquet.

Two indices, because they answer different questions - both over a **fixed
item basket**, since the set of items sampled drifts month to month and
district to district, and an index over "whatever was recorded" measures the
sampling rather than the prices:

- **Over time** (`basket.national`, `basket.states`) - a **Jevons index**: the
  geometric mean of each item's price relative to the base month, over items
  priced in *every* month of the window. This is the standard
  elementary-aggregate formula when expenditure weights are unavailable, which
  they are: DOSM publishes no per-item CPI weights at this granularity. So it
  is equal-weighted, and the UI must not call it "inflation".
- **Across places** (`districts[].idx`) - a **spatial price level**: each
  item's district median over its national median, then the geometric mean of
  those ratios. `100` = the national average basket. Summing raw local prices
  instead would rank districts by which items they happen to stock.

`cheapest` ranks premises within their *own* district on the same relative-price
basis, never on a raw basket total - a shop carrying only the cheap half of the
basket must not be reported as the cheapest shop in town. A premise needs 15+
basket items before it is ranked at all.

`itemGeo` holds the spatial index **per item** rather than collapsed to one
number per district: for each basket item, the 5 cheapest and 5 dearest
districts, as a percentage against that item's national median. Multiplying it
back through the item's national median gives the local ringgit figure the UI
shows ("Where it's cheapest" under Biggest movers). Only the tails ship - the
full 198 × 166 matrix is ~400 KB of uninteresting middle, against ~44 KB for
the extremes. A district needs 5+ recorded prices for that item and must
already carry a spatial index, so one that failed the basket thresholds cannot
reappear at item level. That floor applies to `itemGeo` alone: adding it to the
district index would silently move every published district number.

**What it does and does not answer.** "Where is chicken cheapest" - yes,
district by district. "Which *shop* has the cheapest chicken" - no, and not
from this dataset: premise × item is sparse (most premises price a fraction of
the basket) and the matrix is far too large to ship. Basket-level `cheapest`
remains the answer for "which shops near me are cheap". Note also that
PriceCatcher records specific brands and pack sizes, so part of any gap is
which variety gets stocked locally rather than what it costs - the UI says so
beneath the table.

Sanity checks that the numbers are right, not merely plausible:

- The Aug 2025 → Aug 2026 basket change is **+1.27%**, against DOSM's official
  CPI for food & non-alcoholic beverages (`cpi_headline_inflation`, division
  `01`) at **+1.4%** over the same window. Independent method, independent
  source, same answer.
- The most expensive districts are Nabawan (120.9), Belaga (119.5) and Batu
  Niah (116.5) - remote Sabah/Sarawak, which is the expected result.
- Prices outside `[0.2x, 5x]` of an item's median are dropped as unit-entry
  errors before any median is taken (~0.02% of rows).
- `collect_prices.yml` refuses to publish if the basket falls under 80 items,
  the index has gaps or leaves `40..250`, or coverage drops below 100
  districts. A silently-wrong index is worse than a stale one.

The current month is always partial (it gains a day of prices daily); the
payload flags it as `partial` so the UI can mark that point.

---

## Places: sub-national population + constituency socioeconomics

The national population overview is the only level the OpenAPI serves.
Everything below it - which the dashboard's Population section shows in its
Places sub-block - is Parquet-only on `storage.dosm.gov.my` (note the *dosm*
host, not `storage.data.gov.my`):

- `population_state` - every state, back to 1970, with ethnicity, age-band
  and sex breakdowns at the latest year. The OpenAPI's copy froze at 2023;
  the Parquet runs to the current year.
- `population_district` - 160+ districts with year-over-year growth.
- `population_parlimen` / `population_dun` - all 222 parliament and 600
  state-assembly seats with population and citizen counts.
- The constituency socioeconomics (`hh_income_*`, `hh_poverty_*`,
  `hh_inequality_*`, `lfs_*` at both levels) *are* on the OpenAPI and come
  over the catalogue API.

`tools/collect_geo.py` reads the Parquet with pandas/pyarrow (same deps as
`collect_prices.py`) and writes `public/geo.json` (~150 KB) weekly -
`.github/workflows/collect_geo.yml`, Monday 14:00 UTC. The dashboard's Places
section is a state-first explorer: pick a state, read its trend and
composition, then its districts and seats.

Two gotchas the collector has to work around:

- **The constituency tables advertise age and ethnicity but carry neither** -
  `age` and `ethnicity` only ever hold overall/citizen/noncitizen, so a
  voting-age population per seat is not derivable. The UI labels citizen
  count as an electorate *proxy* (it still includes everyone under 18).
- **Citizenship lives in the `age` column** for the multi-year series
  (`age='citizen'`); the `ethnicity='citizen'` rows exist for one year only.
  State and district tables do carry real age bands and ethnicities, so only
  the constituency tables are affected.
- **The socio join key is the full seat label** (`P.149 Sri Gading`), not the
  code - DUN numbers restart in every state, so keying on the bare code would
  silently collapse 600 seats into 82.

There is no election data on data.gov.my - no results, candidates or voter
rolls. This is "know your constituency", not results.

Public holidays ride along in `slow.json` (`tools/collect_slow.py` reads
Google's public Malaysia calendar) so the KTMB ridership chart can label the
days travel patterns break around - the Feb 2026 Komuter spike is Chinese New
Year, and the level shift after it is Ramadan. The calendar carries no
per-state codes and only reaches back to 2021, which matches the ridership
series.

---

## Forecasts and the daily briefing

`tools/collect_insights.py` writes two files: `forecasts.json` (statistics) and
`insights.json` (a bilingual "Today in Malaysia" briefing). The governing rule
is **statistics for numbers, the model only for words**, and it is enforced in
code rather than requested in a prompt.

### What is deliberately NOT forecast

Every candidate was measured against this repo's own committed data before
anything was built:

| Series | Measurement | Verdict |
| --- | --- | --- |
| RON95 | 26 distinct values in 104 weeks, spanning a subsidy peg at 2.05 and a float at 4.27 | A policy regime break, not a stochastic process |
| RON97 / diesel | 60 and 67 changes in 104 weeks, but still ceilings set weekly by MOF | A committee decision is not a time series |
| USD/MYR | One-step MAE over the last 250 obs: naive `tomorrow = today` **0.00991**, drift model **0.01022** | Extrapolation loses to the flat line. Textbook random walk |
| CPI | Monthly, ~6-week publication lag, ~24 usable points | Too weak, and "predicted inflation" invites misreading |
| Rice | Price-controlled item | Same objection as fuel |

**Nothing here forecasts a price set by government**, and the workflow's
validation step fails the build if one ever appears in the output. If a
forecast is requested for one of these, re-run `backtest_gain()` first: the
measurement decides, not the request.

### What is forecast

Human-routine count series, where knowing last week's same weekday beats
knowing yesterday. Measured gain of seasonal-naive over naive:

| Series | Gain |
| --- | --- |
| Blood donations (type A) | +55.5% |
| Blood donations (all) | +55.3% |
| Shuttle Tebrau ridership | +47.1% |
| Komuter ridership | +27.2% |
| Komuter Utara ridership | +9.6% |
| _ETS rail_ | _-3.0% (rejected)_ |
| _Intercity_ | _-10.6% (rejected)_ |

A series must beat naive by 5% to be published at all, the gain is computed at
collect time, and it ships alongside the numbers so a forecast that quietly
degrades is visible rather than silent.

Method is **seasonal-naive with empirical 10th/90th-percentile bands** over a
trailing window, so the interval reports the accuracy the estimator actually
achieved on that series instead of assuming a distribution. `statsforecast` is
deliberately not a dependency: numba + scipy + llvmlite is a slow, fragile CI
install for gains no backtest here has demonstrated.

Two details that are easy to get wrong:

- **Holidays are neutralised before fitting.** Chinese New Year roughly doubles
  Komuter ridership. Left in, it is a 20-sigma false anomaly every year *and*
  the base the following week gets forecast from. The holiday table in
  `slow.json` says which days to exclude; the chart still marks them.
- **Lags are counted in days, not observations.** Compacting the gaps out of a
  dense series first would make "seven back" mean seven *readings* ago.
  Komuter's history carries 1,060 leading gaps, so that is not seven days.

### The grounding gate

`ground()` extracts every numeral from the model's output and drops any bullet
containing one that is not present in the facts handed to it. A prompt saying
"do not invent data" is a hope; this is the control. Without it the project
eventually publishes a hallucinated figure under a `.gov.my` attribution, which
is not a recoverable error for a dashboard whose whole value is being
trustworthy about official numbers.

It strips currency prefixes so `RM3.77` reads as the quantity `3.77`, and
ignores digit runs glued to letters so `RON95` and `B40` are read as names
rather than claims. Both language versions must pass: a number invented in only
the Malay half is still a number we published.

### Detect first, narrate second

Anomaly detection runs *before* the model sees anything: seasonal residuals
beyond 2.5 sigma against a 365-day trailing baseline, with public holidays
excluded because they are explained rather than anomalous. Only what survives
that filter reaches the prompt, so a quiet day produces a short brief instead
of filler.

Without a `GOOGLE_API_KEY` the collector writes an empty briefing and exits 0 -
the band hides and the rest of the site is unaffected. The forecast half needs
no key at all.

---

## Travel Outlook

`tools/collect_travel.py` (weekly, Monday 01:30 UTC) turns the holiday + KPM
school calendar - already mirrored into `slow.json` from the mycal API - into
the **next 8 weeks of peak travel periods**: school breaks, public holidays and
long weekends, each with an impact level (`extreme` / `high` / `moderate`) and
one English sentence written by Gemini. (English only, in both UI languages:
the prompt asks for no other language. A machine-translated second line under
every card doubled the height of a block whose point is to be compact.) It is
rendered **in the hero**, in the right-hand column the KPI card strip used to
occupy (beside the location and daily briefing on desktop, stacked under them
on mobile): a **scroll-snap card deck** with traffic-light impact badges, a
`NOW` marker plus amber banner when a visitor arrives during a live peak (e.g.
the Term 2 break overlapping Merdeka Day), and a collapsible tips list. The
next-holiday and school-session chips (previously a slim row under the hero
location bar) live inside the band above the deck - same calendar, one travel
block.

The same governing rule as the briefing applies, and it is enforced in code:

- **The calendar is the ground truth, the model writes words.** Gemini only
  ever receives dates `>= today` - holidays in the past are dropped, ongoing
  school breaks are clamped to start today, and fully-finished breaks are
  removed - so it cannot emit a past date. Every period it returns is
  cross-checked against the calendar facts; a period whose start or end is not
  in that set is discarded, never corrected.
- **No key, rate limit or bad JSON falls back to a deterministic outlook**
  built from the same calendar (school break + major festival = extreme,
  break alone = high, other holidays = moderate), so the card always renders.
- The client filters `end >= today` again, so even a stale cached copy never
  shows a past peak.

KV key `travel`, workflow `collect_travel.yml`, sw.js exclusion list updated.

---

## Architecture

```
public/
  index.html            markup + shell (SEO snapshot in <noscript>)
  styles.css            design system + layout (was inline in index.html)
  app.js                all app logic (was inline; CSP has no unsafe-inline for scripts)
  sw.js                 service worker (offline shell + API fallback)
  manifest.webmanifest  PWA manifest
  icons/                generated PNGs (192, 512, apple-touch)
  vendor/               self-hosted Chart.js, Leaflet (SRI-pinned)
src/
  index.js              Worker: static assets + /api/reverse, /api/geocode, /api/gtfs, /api/fids, /api/rapid, /api/flood, /api/alerts, /api/rapid-alerts, /api/aqi, /api/quakes
tools/
  make-icons.mjs        regenerates the icons (no image dependencies)
  collect_radar.py      Trend Radar collector (see above)
  collect_health.py     KKM health collector → public/health.json
  collect_slow.py       slow-data collector → public/slow.json
  collect_prices.py     PriceCatcher basket index → public/prices.json
  collect_geo.py        sub-national population + seat socioeconomics → public/geo.json
  collect_insights.py   forecasts + daily briefing → public/{forecasts,insights}.json
  collect_rapid.py      latest Rapid KL PULSE alert via r.jina.ai → public/rapid_alerts.json
  collect_hotel.py      quarterly Paid Accommodation Survey infographic → public/hotel.json
  collect_election.py   latest SPR election results per category → public/election.json
  collect_traffic.py    InfoTrafikGZ highway posts → public/traffic.json
  collect_tomtom_traffic.py  TomTom urban incidents by region → public/traffic_incidents.json
  collect_alerts.py     MET + USGS earthquakes and JPS flood summary → public/alerts.json
  embed_seo.py          injects live values into index.html + writes feed.xml
wrangler.jsonc
```

The Worker serves `public/` through the `ASSETS` binding and owns the API
routes - `/api/reverse`, `/api/geocode`, `/api/gtfs`, `/api/fids`,
`/api/rapid`, `/api/flood`, `/api/alerts`, `/api/rapid-alerts`, `/api/aqi`
and `/api/quakes`. Everything else is static.

> Static assets are served by Cloudflare's asset router **without invoking the
> Worker**, so response headers for them come from `public/_headers`, not from
> `src/index.js`.

### Why there is a Worker at all

Most routes exist because the upstream API cannot be called from the browser,
or because the payload needs slimming server-side. The weather section can
centre itself on wherever you are, which needs reverse geocoding. That call
cannot be made from the browser:

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
CORS on the *redirect target*. That is fragile - any network layer that
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

The fourth route, `/api/rapid`, backs the Live section's Rapid KL buses. The
data.gov.my GTFS-RT feed for Prasarana is frequently empty even mid-service,
but the operator's own kiosk (myrapidbus.prasarana.com.my/kiosk) shows 800+
live buses, streamed from a socket.io server. socket.io's engine.io POLLING
transport is plain HTTP, so the Worker consumes it without a websocket client:
open the session, connect, emit `onFts-reload`, poll - the response frame
carries base64(gzip(JSON)) which the Worker decompresses, slims to the fields
the map renders, and edge-caches for ~25 s so every visitor shares one
upstream poll. The page aggregates those buses into route chips and grid
clusters on the map (dissolving into individual markers as you zoom), so 800+
points never freeze the browser.

The fifth route, `/api/flood`, backs the flood tile in the Warnings & Hazards
section. JPS's public info
banjir site publishes its live gauge telemetry as a ~1.3 MB static JSON file
(`latestreadingstrendabc.json`) on the WordPress theme path - the old
`/waterlevel/` endpoints are gone. The Worker fetches it server-side, keeps
only stations at **danger / warning / alert with a reading in the last 24
hours** (the feed also carries dead gauges whose last reading is months old),
slims each station to name, coordinates, level, threshold margin, trend and
timestamp, adds a per-state count, and edge-caches for 5 minutes (upstream
telemetry updates every 15). The page renders status-coloured markers on the
map and one chip per station with the details in a tooltip.

The sixth route, `/api/rapid-alerts`, serves the latest Rapid KL service
alert card. myrapid.com.my sits behind Incapsula (a JS-challenge WAF), so no
plain HTTP client - page, RSS, or its wp-json (which answers `401
rest_forbidden` for anonymous reads) - can reach the PULSE alerts. The
route's primary data is the `rapid` KV key written every 10 minutes by the
`collect_rapid` workflow, which scrapes the page through the **r.jina.ai
reader proxy** (from GitHub's IP pool - jina's free tier rate-limits
Cloudflare Worker egress to null) and parses the newest post. The route
falls back to a live jina fetch on cold start, and the dashboard reads
`rapid_alerts.json` same-origin (KV first, committed file as cold-start
copy), the same pattern as the other collectors.

The seventh route, `/api/aqi`, backs the air quality tile and alert card.
The official APIMS feed (eqms.doe.gov.my) resets connections for non-browser
clients, so the Worker polls **Open-Meteo's air-quality model** (free,
keyless - the same provider the weather section already uses) for **18 major
cities** via a single, fast batch coordinates request, returns every station's US AQI and PM2.5 sorted
worst-first plus the cleanest for comparison, and edge-caches 10 minutes
(the model updates hourly). The frontend features a resilient 3-tier fallback (Worker KV -> static `aqi.json` -> direct client-side Open-Meteo batch query) ensuring zero data dropouts. The page renders one comparison card per city;
the alert deck only gains an AQI card when the worst city is Unhealthy
(US AQI 101+, the haze threshold).

### Earthquakes: why two sources

MET Malaysia publishes a global earthquake list through data.gov.my, and it
is the obvious source for a Malaysian dashboard. It stopped being live.

Checked on 15 Aug 2026 with the cache bypassed (`cf-cache-status: BYPASS`, so
this was the origin's own answer): 836 events whose newest was **six days
old**, and no sign of that morning's **M6.9 at Pematangsiantar** in North
Sumatra - 268 km from the Perak coast, comfortably inside the 500 km radius
the page filters on. Over the preceding 30 days MET listed **2** events within
500 km; USGS listed **8**.

So USGS runs as the live source, through `/api/quakes`. It is proxied rather
than fetched directly because `connect-src` in `public/_headers` is a
deliberate allowlist and `earthquake.usgs.gov` is not on it - and proxying
also edge-caches one fetch of a ~1.6 MB worldwide feed across every visitor
and slims it to the fields the cards use. MET is still merged in for the
events it does carry: it is the Malaysian authority, and its rows carry the
local bearing text ("268km SW Bagan Datuk, Perak") that USGS has no notion
of. The same rupture reported by both differs slightly in origin time and
epicentre, so "same event" is a tolerance - two minutes and 150 km - and
MET's row wins. Cards name their source.

Two windows, deliberately: the deck carries **7 days** because quakes that
close happen about 1.5 times a month, and a 12-hour window (what this used
to be) put a card on screen roughly 0.3% of the year - the feature was
invisible, and there was no way to tell working from broken. The nav badge
counts only the last **24 hours**, because "active alert" has to keep
meaning *now*.

### The traffic ticker

The strip under the nav merges two feeds into one row - deliberately one row;
the page has enough bands above the fold already.

**Highway posts** come from the InfoTrafikGZ Telegram channel, which is the
concessionaires' own reporting (PLUS, KESAS, LDP, MEX, KL-Karak) and almost
exclusively highways. **Urban incidents** come from TomTom's Traffic Incident
Details v5 for 10 regions, which is the city-street layer the highway feed
never mentions - and it is scoped to the visitor's region, matched from their
coordinates against each region's bounding box (a hand-picked place is matched
by name, since MET's forecast locations carry no coordinates). A visitor in a
state no region covers is shown nothing rather than another state's roads.

Both sources are held to the same **2-hour** freshness rule. A live-traffic
strip has no room to timestamp itself beyond each post's own clock, so an old
report does not merely fail to help - it misleads. That rule is why the TomTom
collector runs hourly rather than a few times a day.

The two are **interleaved**, not concatenated. Appended, the TomTom half was
9,917px into a 12,587px strip on a 110s cycle - about 87 seconds before one
appeared. (And before that it was unreachable at any duration: both duplicated
`.traffic-run` spans were animated by `-50%` of their *own* width, so each slid
half its width and snapped back, and only the first half of the list ever
crossed the window. It is `-100%` now - one full run, which is the seamless
case the duplicate span exists for.)

### Security

- **CSP with no inline script execution**: the app's JS lives in `/app.js`,
  so `script-src` has no `'unsafe-inline'` - inline scripts, inline event
  handlers and `javascript:` URLs are all refused. `style-src` keeps
  `'unsafe-inline'` for ~200 dynamic inline styles (charts, skeleton
  widths) - style injection cannot exfiltrate data or execute code. Plus
  no `'unsafe-eval'`, `object-src 'none'`, `frame-ancestors 'none'`,
  `form-action 'none'`, and a `connect-src` allowlist.
- **HSTS with `preload`** (`max-age=31536000; includeSubDomains`), `nosniff`,
  `X-Frame-Options: DENY`, `Cross-Origin-Opener-Policy: same-origin`,
  `Cross-Origin-Resource-Policy: same-origin`, `Origin-Agent-Cluster`,
  a restrictive `Permissions-Policy` (only `geolocation`, same-origin) and
  `strict-origin-when-cross-origin` referrer policy. All in
  `public/_headers`.
- **Chart.js and Leaflet are pinned and SRI-checked**
  (`integrity="sha384-…"`), so altered bytes are refused rather than executed.
- Both API routes **validate input against a strict allowlist** and never
  interpolate user input into an upstream URL, and they reject cross-origin
  callers - they exist for this page, not as a public proxy.
- No secrets, tokens or account identifiers are in the repo; the app needs
  none. `.dev.vars` and `.wrangler/` are gitignored.
- No analytics. The page connects to a short allowlist: itself (static assets
  and `/api/*`), `api.data.gov.my` (every dataset, health included),
  `api.open-meteo.com` (weather live conditions), and
  `tile.openstreetmap.org` (map tiles in the Live section). Every library is self-hosted. The "Buy me a coffee" button is a
  plain link, not their tracking widget. Earthquake and live-vehicle cards
  include an outbound Google Maps link - a normal link the reader chooses to
  follow, not a request the page makes.

---

## Working with the API

Notes that cost time to discover - all verified against live responses.

**A trailing slash is required.** `GET /weather/forecast?limit=1` responds
`301` to `/weather/forecast/?limit=1`. Every URL the app builds ends in `/`, so
no request wastes a redirect hop against the rate limit.

**Rate limit: 4 requests per minute, per API family** (`weather`,
`data-catalogue`, `opendosm`, `gtfs-static`, `gtfs-realtime`). The app:

- fetches each family once per session, strictly sequentially, ~1.2 s apart;
- never lets two calls to the *same* family land within 3 s - bursts trip the
  limiter even when the per-minute count is legal;
- enforces a rolling 4-per-60 s token bucket per family;
- caches results in memory + `localStorage` for 15 minutes;
- never polls. Refresh is manual.
- retries transient failures once (network blips and 5xx get a 1.5 s / 2.5 s
  pause, then a second attempt); 429 and 404 are not retried - the first is a
  quota state a retry won't fix, the second is permanent. A section that
  still fails shows an error box with a manual Retry button, keeping any
  stale content on screen.

Total cold load: **3 requests** - weather 3 - plus the real-time feeds
(transport GTFS + live vehicles, which must stay live) and the static
`health.json` / `slow.json` (same-origin, produced by the daily collectors,
no API budget spent). GitHub is not called at all. Only weather + fuel (fuel
reads slow.json) are fetched on first paint; everything else is lazy-loaded
as its section scrolls into view, so the first screen renders before the
slowest datasets arrive.

**Dataset ids that exist** (many plausible ones do not - an unknown id returns
`404` with `{"status_code":404,...}`):

- `data-catalogue`: `fuelprice`, `hh_income`, `exchangerates`,
  `interestrates`, `poskod` - plus `arrivals`, `passports`, `births` and
  `mnha`, which exist but are frozen (see *Data freshness* below), and
  `blood_donations`, `organ_pledges`, `pekab40_screenings`, which the KKM
  collector uses (see above)
- **Parquet-only, not on the OpenAPI at all** (`exclude_openapi: true`, so
  `?id=` returns 404): `pricecatcher`, `lookup_item`, `lookup_premise`,
  `registration_transactions_car`, `ridership_od_*`, and the sub-national
  `population_state` / `population_district` / `population_parlimen` /
  `population_dun`. These live on `storage.data.gov.my` and must be read as
  Parquet - see the PriceCatcher and Places sections above
- `opendosm`: `cpi_core`, `cpi_headline`, `lfs_month`, `gdp_qtr_real`,
  `fdi_flows`, `population_malaysia`
- Not found: `electrictariff`, `watertariff`, `interestrate`, `unemployment`,
  `cpi_2d`, `opr`

**Gotchas in the catalogue datasets** (all verified against live responses):

- `interestrates` has **no `opr` series** - the rate codes are lending and
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
interleaved on the same dates - charting the raw response draws a sawtooth
through zero.

**Locations are keyed by `location_id`, not name.** The forecast feed has 360
distinct ids but only ~284 distinct names: "Perlis" exists as a state
(`St001`), a district (`Ds002`) and a town (`Tn001`), each with its own
forecast. Keying by name silently merges them. Prefixes are `St` state,
`Ds` district, `Tn` town, `Dv` division, `Rc` recreation.

**MET free text arrives with HTML entities already encoded** (`&amp;`), so it
must be decoded before escaping or readers see the raw entity. The warnings
endpoint also carries "No Advisory" all-clear notices with `null` validity
dates - `new Date(null)` is the epoch, which renders a bogus
"valid 01 Jan 1970". Both are handled.

**GTFS static** ships as ZIP. `routes.txt` column *order* differs between
agencies, so CSV is parsed by header name. For the bus feeds only
`routes`/`trips`/`stops`/`agency` are inflated - Prasarana's `stop_times.txt`
alone is 5.6 MB of the 8.8 MB archive and is never decompressed. The rail feed
(`gtfs_rapid_rail_kl.zip`) is the exception: its `stop_times.txt` is small
enough to read, which is how the LRT/MRT metro diagram gets the ordered
station sequence per line. It also carries the official route colors
(`route_color`) used to draw each line.

The rail feed is served by the same `/gtfs-static/prasarana` endpoint with
`category=rapid-rail-kl` - 187 stations across 8 lines (Ampang, Sri Petaling,
Kelana Jaya, Shah Alam, MRT Kajang, MRT Putrajaya, Monorail, BRT Sunway).

**GTFS realtime** (KTMB) legitimately returns zero vehicles outside service
hours. That is an empty state, not an error - the UI says so and shows the
feed's own timestamp as proof it responded. Rapid KL buses do **not** use the
GTFS-RT feed (it is frequently empty even mid-service); they come from
Prasarana's kiosk feed via `/api/rapid` instead - see the Worker section above.

---

## No-dependency implementations

Three things that would normally pull in a library:

- **ZIP reading** - a central-directory reader using the platform's
  `DecompressionStream('deflate-raw')`. No JSZip.
- **GTFS-Realtime protobuf** - a ~90-line wire-format reader (varint /
  length-delimited / fixed32) covering just the `VehiclePosition` subset
  (used for KTMB trains; Rapid KL buses come through `/api/rapid` as plain
  JSON). No protobufjs, no `.proto` file.
- **Icons** - `tools/make-icons.mjs` renders the PNGs with a hand-written
  encoder (`zlib` + CRC32), supersampled 4× for clean edges.

Chart.js and Leaflet are the only runtime dependencies. They live in
`public/vendor/` (self-hosted with subresource integrity, so there is no CDN
to go down and the app works fully offline) and are precached by the service
worker.

### Compacting daily series

Several datasets are one JSON object per category per day - blood donations
alone are five keys over three years. `denseDaily()` collapses each key to a
start day plus a flat array of values, which is roughly a fifth the size and
keeps these sections inside the localStorage budget the other eight share.
Seven-day moving averages are computed at render time rather than cached, for
the same reason.

## Preferences

All preferences are stored in `localStorage` only - nothing leaves the device:

- **Theme** - dark, light, or follow the system, plus a persisted choice.
- **Text size** - a large-text mode for readability.
- **Language** - English or Bahasa Melayu for the interface. Weather warnings
  use the API's native `_bm` fields when available, and Malay forecast phrases
  are mapped to English when the interface language is English.

The live maps use OpenStreetMap tiles (© OpenStreetMap contributors), with a
CSS filter to keep them dark in dark mode. The `img-src` CSP allows
`tile.openstreetmap.org` for exactly that purpose.

---

## Caching

Two layers, deliberately different:

- **App (`localStorage`, 15 min TTL)** - drives freshness. Holds compacted view
  models, not raw responses: forecast strings are dictionary-compressed, and
  GTFS is reduced to counts plus stop coordinates before storage. A full cold
  load is a few hundred KB, well under quota, and `cacheSet` degrades to
  memory-only if the quota is hit anyway.
- **Service worker** - drives offline. Cache-first for the shell;
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
`/api/fids` all working locally - `wrangler dev` picks up the `FIDS_API_KEY`
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
production deploy - no workflow file, secrets, or manual steps required.

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
is welcome - a 1970-2026 population series is more useful than a short one -
but a series whose *last* update is years old has nothing to compare against,
and charting it invites readers to mistake stale numbers for today's.

So: the pill in each section header shows **"data as of &lt;date&gt;"** - the
newest row that section actually renders, not when we fetched it - and appends
**"⚠️ may be delayed"** once that date is older than the section's tolerance
(`MAX_AGE_DAYS` in `index.html` - roughly twice each source's publication
interval, so annual series like population get ~14 months while daily feeds
get 1-3 days). The date comes from `LOADERS[id].asOf(data)`; a section that
returns nothing (a static lookup, a live feed) keeps the old "updated HH:MM"
fetch time instead.

Datasets that had stopped updating entirely were removed rather than captioned:

| Removed | Last update |
| --- | --- |
| `arrivals`, `passports` (the whole Tourism section) | 2024-10-01 |
| `births` | 2023-07-31 |
| `mnha` (national health accounts) | 2022-01-01 |
| `population_state` (the OpenAPI copy froze at 2023; the full series now
  returns via `geo.json` - see the Places section) | 2023-01-01 |

`poskod` is exempt: it is a static reference table, not a time series, so it
has no publication date that can go stale. It defines no `asOf`, so its pill
keeps showing the fetch time.

---

## Adding a dataset

**Into an existing section** - add one request to the relevant loader in
`index.html`, reduce it to a compact array, and render it. Mind the 4/min cap:
`weather` is the only family still hit live (3 of 4); the `data-catalogue`
and `opendosm` families are served by the daily collectors' static files, so a
new series there should be added to `tools/collect_slow.py` instead of the
browser loader - that keeps the visitor path static.

```js
const x = await request("data-catalogue", "/data-catalogue", { id: "YOUR_ID" });
```

**As a new section** - two registrations, and the rest is automatic:

```js
SECTIONS.push({ id:"myid", label:"My Data", icon:"🧭", family:"data-catalogue" })
META.myid    = { title, desc, how, eps:[...] }
LOADERS.myid = { load, render, after, asOf }
// after(data) runs side-effects once the section renders (e.g. loading a
//             merged sub-block).
// asOf(data)  returns the newest data date the section renders, for the
//             "data as of …" pill. Omit it and the pill shows the fetch time.
```

Nav entry, scroll-spy, skeleton, error/retry, caching and throttling are all
wired from those (new sections load eagerly; `LAZY` in `index.html` marks the
scroll-triggered ones). Browse available ids at
[developer.data.gov.my](https://developer.data.gov.my).

---

## On-device AI suite (Chrome Prompt API / Gemini Nano)

**Experimental, and off for almost everyone.** When supported by the browser,
the dashboard mounts on-device AI features that run Gemini Nano locally:
- **Per-section Summarise**: Compresses section prose and structured KPIs into three bullets.
- **Ask MyGov Assistant**: Answers natural language questions directly over in-memory datasets with an intelligent QA extraction engine, state-specific demographic resolution (population, ethnic splits), interactive deep links, and client-side open data fallback search.
- **My Day Brief**: Synthesizes localized weather, public transport alerts, fuel prices and holidays into a daily morning commute and living brief.
- **Explain Metric Simply (ELI5)**: Adds plain-language citizen impact notes and breakdown tooltips to technical macroeconomic indicators (OPR, CPI inflation, Real GDP).
- **Voice Readout (`aiSpeak`)**: High-performance speech synthesis engine with voice selection, queue hardening, and audio toggle.

Nothing is sent anywhere: models execute purely in the browser process, so there is no new `connect-src` entry and zero server cost.

All AI controls are only built when `await LanguageModel.availability() !== "unavailable"`. Everywhere else `mountAI()` returns before touching the DOM, so the page is byte-identical to standard rendering.

| | |
|---|---|
| Engine | Desktop Chrome 148+ only. Firefox, Safari and Edge do not implement this - Mozilla, Apple, Microsoft and the W3C all objected to it shipping. |
| Hardware | ~22 GB free storage, plus 16 GB RAM or 4 GB VRAM. |
| First run | Downloads a multi-GB model; the panel shows a progress bar (`monitor` -> `downloadprogress`). |
| Mobile | Not supported at all - which is most of this site's traffic. |

### The origin trial

`LanguageModel` itself is **on by default** in Chrome 148+ and needs no token.
The `<meta http-equiv="origin-trial">` in `index.html` is for
**AIPromptAPIParams**, a separate trial that only unlocks the `temperature` and
`topK` options on `create()`. It is bound to `malaysia-at-a-glance.com` with
`isSubdomain`, so it covers `www.` but **not** the
`mygov.faizalmzain.com` staging deploy (different apex) or `localhost`.

**It expires 2026-10-06.** After that `LanguageModel.params()` starts failing,
`aiCreate()` drops `temperature`/`topK` and retries bare, and summaries quietly
run at default sampling. Nothing breaks and nothing is logged - so if the
output gets looser around October, this is why. Re-register at
[developer.chrome.com/origintrials](https://developer.chrome.com/origintrials)
if the trial is still open.

Origin-trial tokens ship in the page and are public by design; this one is not
a secret and does not belong in Wrangler vars.

### Grounding & Hardening

The model is handed structured section KPIs and prose and is strictly instructed
never to invent, restate or round any figure not present in the data.
Every number on this site is a published government statistic, and a ~3B
on-device model will confidently mangle a fuel price. The rendered cards remain
the source of truth; the panel carries a permanent "may be inaccurate" note.

Hardening details in `app.js`:
- **In-memory LRU caching**: Generated summaries, explanations and query answers are cached to prevent battery and compute drain on repeated opens.
- **Intelligent Demographic & Fact Resolver**: Direct extraction of state demographics, ethnic counts, and economic indicators with fallback indexing when Gemini Nano is offline or downloading.
- **Model output is untrusted text**: `aiRender()` and query results build the DOM with `textContent` and never `innerHTML`.
- **Model input is untrusted too**: Scraped text and live feeds are wrapped in `<data>` tags, stripped of any closing tag, and the system prompt treats the block strictly as data content.
- **Prompt streaming deltas**: `promptStreaming()` yields deltas, not cumulative snapshots; `aiSummarise()` and `aiAskQuery` accumulate chunks safely.
- **Design System & Contrast Hardening**: Action and voice controls bind directly to `.btn` / `.btn-a` tokens with high-specificity contrast rules for dark and festive themes.

---

## Accessibility

Skip link, `:focus-visible` outlines throughout, `aria-label`s on icon-only
controls, keyboard-operable sortable table headers (`Enter`/`Space`),
`aria-current` on the active nav item, `aria-sort` on sorted columns, and
real `<button>`s for selectable weather rows with an `aria-live` region
announcing location changes. `prefers-reduced-motion` is honoured - it disables
chart animations, counter count-ups and smooth scrolling. Every chart has a
"View data table" alternative for users who can't use tooltips. Body text is
`#e8ecf4` on `#0a0c10` (~16:1 contrast); the dimmest supporting text stays
above 4.5:1 in both themes.

---

## Licence & attribution

Code: MIT. Data © Government of Malaysia, via the
[Open API](https://developer.data.gov.my) - MET Malaysia, MOF, DOSM, KTMB and
Prasarana. Reverse geocoding © OpenStreetMap contributors (ODbL).
