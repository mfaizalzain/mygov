Add these NEW sections/upgrades to the mygov dashboard. Everything else is
already built — do NOT touch existing sections, loaders, or the design system
except where explicitly noted. All dataset ids below were VERIFIED live on
2026-08-09 via the data.gov.my API. Use the mygov MCP tools to double-check
response shapes before wiring each one.

## 1. Transport cluster (JPJ / KTMB / MoT) — NEW sections
- **Vehicle registrations by fuel type** (registrations_type_fuel, monthly,
  data to 2026-07): stacked bar chart of new registrations split by fuel
  (electric / hybrid / petrol / diesel / greendiesel / other) over time, plus
  a KPI for latest month EV registrations. This is THE EV adoption chart.
  Filters: fuel type toggle. data as of 2026-07-01.
- **KTMB ridership** (ridership_ktmb_daily, daily, data to 2026-08-08):
  line chart of daily ridership by service (ets / intercity / komuter /
  komuter_utara / shuttle_tebrau as available), 7-day MA overlay, service
  selector. Complements the existing GTFS live section with real passenger
  numbers. data as of latest.
- Do NOT add rapid rail (Prasarana) — not on the public API (dashboard-only).

## 2. Finance cluster (BNM / PayNet) — NEW + upgrade
- **FPX e-payments** (trnsc_daily_fpx, DAILY, data to 2026-08-08): line chart
  of daily transaction value + volume. KPI: latest day value (RM B). This is
  real-time payments pulse — very compelling. data as of latest.
- **Upgrade exchange rates**: add exchangerates_daily_1200 (daily MYR rates)
  as a second granularity option next to the existing monthly exchangerates —
  same chart, "daily / monthly" toggle. Keep existing section otherwise.
- **Payment instruments** (payment_instruments, monthly, 2026-02): small bar
  chart of transaction value by instrument type (charge_f2f etc.) — optional,
  only if rate-limit budget allows (finance family).

## 3. Economy upgrades (DOSM) — extend existing economy section
- **CPI by state** (cpi_state, monthly, 2026-06): add a state selector to the
  existing CPI chart (or a small state-comparison bar chart). Keep cpi_core
  as-is.
- **Headline CPI** (cpi_headline, monthly, 2026-06): add as a second line
  alongside cpi_core (headline vs core — the classic comparison).
- **FDI flows** (fdi_flows, quarterly, 2025-07): bar chart of inflow/outflow/
  net by quarter. Optional if budget allows.
- **EPF dividend** (epf_dividend, yearly, 2025): tiny KPI card — latest
  shariah + conventional dividend rates. Cheap, high recognition.
- NOTE: population_district returns EMPTY via the API — do not build it.

## 4. MoH health — SWAP to JSON API (simpler than parquet)
Replace the planned parquet/hyparquet approach with the catalogue API — the
SAME daily series exist as clean JSON (no parquet parsing, no
raw.githubusercontent CSP entry needed):
- blood_donations (daily, 2026-08-08): date, donations, blood_type (all/a/
  b/ab/o) — line chart of daily donations + blood-type split.
- organ_pledges (daily, 2026-07-05): date, pledges — trend line.
- pekab40_screenings (daily, 2026-08-02): date, screenings — trend line.
- Keep the "Health data updated:" header from metadata_updated_date.json or
  use the latest API date per series. Keep "Data: MoH via data.gov.my"
  attribution. REMOVE any hyparquet/parquet code you may have started.

## 5. Population section (OpenDOSM) — NEW
- population_malaysia (quarterly/yearly, 2026-01-01): KPI total 34.39M +
  YoY; line chart 1970→present (age=overall, sex=both, ethnicity=overall);
  donut of ethnicity split at latest date. data as of 2026-01-01. Note:
  population_state is excluded per freshness policy (frozen 2023); use
  national series only.

## Rules
- Follow the existing design system exactly (CSS variables, cards, chart
  theming, skeletons, tooltips, "data as of" headers, tabular-nums).
- Mind the 4/min per-family rate limit: new data-catalogue ids share the
  catalogue family bucket; opendosm (population, cpi) shares its own. Fold
  new fetches into the existing token buckets; do NOT exceed them. Lazy-load
  new sections.
- Bump CK cache prefix (mygov.cache.vN.) since loaders change.
- Update CSP connect-src ONLY if a new host is needed — the JSON-API swap
  should REMOVE the raw.githubusercontent.com need, so tighten CSP
  accordingly (drop it if unused).
- Register in SECTIONS/META/LOADERS with lazy load; add nav entries; wire
  KPI feeds.
- Test locally (npx wrangler dev): every new/upgraded section renders real
  data, zero console errors, mobile + dark theme intact.
- Commit ONLY, do NOT push. Report: what was added/upgraded, per-section
  "data as of" values, CK bump value, and any dataset that failed
  verification.
