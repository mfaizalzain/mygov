# Malaysia Calendar (mycal) Upgrade + Declutter - Implementation Plan

> **For Hermes:** Use subagent-driven-development skill to implement this plan task-by-task.

**Goal:** Upgrade the dashboard's holiday data from Google ICS (federal-only) to the mycal API (state-aware + school holidays + is-school-day), add a "current/next holiday" widget, and declutter the top of the page.

**Architecture:** Collector (CI) fetches mycal JSON once daily → mirrors into KV (never hot-link the third-party Worker from the browser) → dashboard reads from KV. Widget + chart markers are client-side from the existing `slow.json`.

**Tech Stack:** Python (collect_slow.py), Cloudflare KV, vanilla JS (public/index.html), mycal API `https://mycal-api.huijun00100101.workers.dev/v1`.

---

## Sources (verified live 2026-08-11)

- Public holidays: `GET /v1/holidays?year=2026&state=selangor` → `{data:[{id,date,name:{ms,en},type,status,states:[...]}]}`
- Today: `GET /v1/holidays/today` (+ `?state=` variant)
- Next: `GET /v1/holidays/next`
- School holidays: `GET /v1/school/holidays?year=2026` → `{data:[{type,group,startDate,endDate,days,name:{ms,en}}]}` (Kumpulan A/B)
- Is school day: `GET /v1/school/is-school-day`
- Terms: `GET /v1/school/terms?year=2026`
- Long weekends: `GET /v1/holidays/long-weekends?year=2026`
- States: `GET /v1/states`, resolve: `GET /v1/states/resolve?q=kl`
- iCal: `GET /v1/feed/ical/{state}`
- Docs: `GET /v1/docs` (HTML), API root: `GET /v1`

## Data shape changes to slow.json

Current `holidays[]`: `[["2021-02-12","Chinese New Year's Day",1], ...]` (date, name, is_federal).

New shape (keep array-of-arrays for size; extend):
```
holidays: [
  ["2026-08-25", "Maulidur Rasul (The Prophet Muhammad's Birthday)", "federal", ["SGR","KUL",...]],
  ...
]
school: [
  {type:"cuti_pertengahan", group:"A", start:"2026-05-22", end:"2026-06-06", name:"Mid-Year Holiday"},
  ...
]
is_school_day: true|false  (from /v1/school/is-school-day at collect time; recomputed client-side from school ranges)
```

Client can compute is-school-day from `school` ranges (date between start/end) - no server freshness dependency.

## Task list (bite-sized)

### Task 1: Swap holiday source in collect_slow.py
- Replace the Google ICS fetch + parse (lines ~89-113) with mycal API calls
- Fetch `/v1/holidays?year={y}` for current ±1 years (federal + all-state entries), `/v1/school/holidays?year={y}`, keep backward-compat: emit both `holidays[]` (new shape) and keep field name
- User-Agent header `mygov/1.0` (Cloudflare-hosted API may block Python-urllib default)
- Graceful fallback: if mycal unreachable, keep yesterday's holidays (do not write empty)
- Run: `python3 tools/collect_slow.py` - verify `public/slow.json` holidays has state codes + school array
- Commit

### Task 2: Widget - current/next holiday + school day in Today in brief header
- `public/index.html`: in `#brief-h` add a trailing span `#hol-widget` (hidden until slow.json parsed)
- New fn `renderHolWidget(d)` in the brief loader path: 
  - today is holiday → `🗓 Today: <name>` (highlight class)
  - else → `🗓 Next: <name> · in Nd` (first holiday with date >= today)
  - school → `🏫 School in session` or `🏫 School break` (if today within any school range)
- i18n keys: "Next holiday", "Today", "School in session", "School break", "in Nd" format
- Verify in browser console: widget renders with Merdeka (2026-08-31, in 20d) + school in session
- Commit

### Task 3: KTM chart markers - state-aware + school breaks
- `holidayMarkers()` (line ~4479): keep working with new holiday shape (index 1 = name, index 2 = federal/state string)
- Add school-break shading: subtle background band over date ranges where school is out (alpha 4-6%), distinct from holiday markers
- Verify: transport section chart shows both marker types without collision
- Commit

### Task 4: Declutter B1 - merge alerts + brief into one "Today" panel
- Combine `#alerts-band` + `#brief-band` into a single `#today-band` with a header row and two groups (alerts on top when active, then brief)
- Keep both hidden states independent (alerts group hidden when nothing active; brief hidden when no insights)
- CSS: reuse .alerts/.brief card styles; single card container
- Verify in browser: with current live data (flood 25 + brief 5 bullets) one panel renders; kill flood → alerts group hides, brief remains
- Commit

### Task 5: Declutter B3 - trim hero KPIs
- Identify redundant hero KPI cards that duplicate section content (FX, fuel, CPI appear in Finance/Economy sections)
- Keep: hottest-today trio + essentials; remove duplicates from hero strip
- Verify: hero renders trimmed set, no broken refs, Lighthouse unchanged
- Commit

### Task 6: KV + workflow + docs
- `kv_upload.py` / collector workflow already push `slow` key - no change needed (holidays ride inside slow.json)
- README: holiday source Google ICS → mycal (link + attribution), school holiday + widget mention
- Update `mygov-dashboard` skill: holiday data source, shape, widget, declutter decisions
- Commit + deploy + verify live

## Declutter Round 2 - Places unification + chip-aware views (added 2026-08-11)

User-driven additions after the district enrichment shipped. Keeps the "fewer, sharper panels" theme.

### Task 7: Merge Population + Places into one explorer with a National chip
- Current: `#body-population` (national trend + ethnicity doughnut) then `#places-sub` (state chips → per-state everything). Two blocks from the same geo.json.
- Change: Places becomes the single explorer. Prepend a **Malaysia** chip to the state chips; `placesState === ""` = national.
- National view: trend = sum of all states' series (geo.state has `years` + per-state `trend` arrays - sum column-wise), eth = sum of state `eth` maps, dists/parl/duns = ALL rows (unfiltered).
- The Population block's KPIs + trend + doughnut are subsumed by the national Places view - remove `#body-population` cards (or keep as the national view's content, decide during impl: aim to delete the duplicate, keeping one chart set).
- `LOADERS.population` still triggers `places` - keep the chain, but `renderPopulation` becomes a thin national render or is removed.
- Verify: default page load shows Malaysia chip pressed; clicking Johor narrows everything; back to Malaysia shows all 164 districts + 822 seats.
- Commit

### Task 8: Chip-aware "Affluent vs poorest" comparison
- `placesCompare()` currently computes the strip nationally (all districts). Change: it must respect the selected chip - national chip → national comparison; a state chip → richest/poorest **within that state**.
- Rename to `placesCompare(dists)` and pass the already-scoped `dists` (national or state-filtered) from `renderPlaces`; the gap multiplier and labels adapt automatically.
- Verify: Johor chip → Johor Bahru (RM 8,977) vs Tangkak (poorest in Johor); Malaysia chip → Ulu Langat vs Bukit Mabong (4.4x).
- Commit

### Task 9: District ethnicity composition display
- The district table already has a "Top group" column (label + %). Enrich: add a compact ethnicity mini-bar per row (6 segments using ETHNIC colors) with tooltip/label on hover, or an expandable row detail.
- Keep the table dense: mini-bar inside the Top group cell (width ~90px) is preferred over a new column.
- Verify: Petaling row shows teal-dominant bar (Bumiputera Malay 47%); hover shows each group.
- Commit

### Task 10: Stale-data accordion (constituency table)
- The Constituencies card (222 P + 600 DUN rows, socio @ 2024) is the heaviest, stalest block. Wrap in native `<details>` collapsed by default; summary line shows the year: `▸ Constituencies · 822 seats · socio 2024`.
- Rule: anything stale >= 2 years becomes collapsible with its year in the label; fresh data stays open (district table, comparison strip).
- Verify: default collapsed; expanding shows the existing seat table + controls; no JS needed (native details).
- Commit

### Task 11: Hero KPI trim (carried from Round 1 Task 5)
- Identify redundant hero KPI cards duplicating section content; keep the essentials (hottest, fuel, flood, live); remove the rest.
- Verify: hero renders trimmed set, no broken refs, Lighthouse unchanged.
- Commit

### Task 12: Docs + deploy for Round 2
- README: Places explorer national-chip + district composition + comparison; constituency accordion note.
- Update `mygov-dashboard` skill: placesState="" national convention, chip-aware compare, ETHNIC mini-bar, stale-accordion rule.
- Commit + deploy + verify live (default Malaysia chip; Johor narrows; comparison follows chip; constituency collapsed).

## Verification (updated)
- `python3 tools/collect_slow.py` → slow.json regenerated with new holiday shape + school
- Local `wrangler dev` + browser: widget shows Merdeka in 20d, school in session; Today panel merged; hero trimmed
- Live after deploy: curl slow.json shows state-aware holidays; browser band OK
- KV push: workflow run success, KV key `slow` fresh

## Risks / notes
- mycal is a third-party Cloudflare Worker - mirror to KV at collect time; if it's down at collect time, keep yesterday's data (collector never writes empty)
- School calendar 2027 not yet published (KPM announces late-year) - collector fetches years present; missing year → no school entries for that year, widget degrades gracefully
- State detection for the widget: use visitor's resolved state (pos-q) when available; fall back to federal view
- MIT license - attribution in README/footer
