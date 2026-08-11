# Tourism Arrivals Collector + MCP Tool - Implementation Plan

> **For Hermes:** Use subagent-driven-development skill to implement this plan task-by-task.

**Goal:** Bring Tourism Malaysia's monthly visitor-arrivals data into the mygov ecosystem: a collector that scrapes the (public, auth-free) monthly top-51 PDFs, extracts the tables to JSON → KV → dashboard "Tourism" section, and exposes the same data as an MCP tool (`mygov_tourism_arrivals`) on the hosted Worker + stdio plugin servers.

**Architecture:** GitHub Action (monthly cron) → `tools/collect_tourism.py` (pattern-probes deterministic PDF URLs, downloads the latest published month, pymupdf table extraction) → `public/tourism.json` → KV key `tourism` → Worker serves `/tourism.json` (KV route) → dashboard section + MCP tool proxies the same JSON. Login is NOT needed for the files (verified 2026-08-11: PDFs return 200 without any cookie; the login-gated index pages merely REVEAL the URLs, which are pattern-predictable).

**Tech Stack:** Python 3 stdlib + pymupdf (text-layer extraction, verified working on `top_51_may_2026_visitor.pdf`: 1 page, clean text table), GitHub Actions cron, Cloudflare KV, vanilla JS dashboard section, MCP tool registration on Worker + Python stdio servers.

**Terms compliance (verified 2026-08-11):** Tourism Malaysia ToU = public use, non-commercial, attribution ("Data provided by Tourism Malaysia"). robots.txt Content-Signals: `search=yes, ai-train=no, use=reference`. Displaying the numbers on the dashboard with attribution is within terms; do NOT feed the raw PDF text into AI training, and keep the collector's Gemini-free (no LLM anywhere in this pipeline).

---

## Verified facts the plan rests on (2026-08-11, live-tested)

1. **PDFs are public** - no cookie: `curl https://data.tourism.gov.my/frontend/pdf/2026/visitor_arrivals/top_51_may_2026_visitor.pdf` → 200 (271KB). Login only reveals the index.
2. **Text-based, not scanned** - pymupdf extracts cleanly. Page structure: rank / COUNTRY / 2026 / 2025 / 2019 / growth% May26/Apr26 / growth% 2026/2025 / growth% 2026/2019, then YTD columns (2026 / 2025 / 2019 + growths). ~51 rows.
3. **2026 URL pattern (current):**
   - `frontend/pdf/2026/visitor_arrivals/top_51_{m}_2026_visitor.pdf`
   - `frontend/pdf/2026/tourist_arrivals/top_51_{m}_2026_tourist.pdf`
   - `frontend/pdf/2026/excursionist_arrivals/Top_51_{m}_2026_excursionist.pdf` (capital T!)
   - Months are **Malay abbreviations**: jan feb mac apr mei jun jul ogo sep okt nov dis (March = `mac`, NOT `mar`)
4. **2014-2025 pattern (archive):** `frontend/pdf/{year}/tourist_arrivals/{n}_top_45_tourist_arrivals_{month}_{year}.pdf` (full month names, n=1..12)
5. **Index inventory (from the login session, cached):** ~249 arrivals + 60 hotel survey + 38 infographics + 17 publications PDFs; arrivals has 2014→2026-05 published so far (monthly cadence, ~1-month lag).
6. **Expenditures page is an empty stub** - no data there; skip it.

---

## Files to change

| File | Change |
|---|---|
| `tools/collect_tourism.py` | **Create** - pattern-probe months, download latest published PDF, extract table, write `public/tourism.json` |
| `tests/test_tourism.py` | **Create** - extraction + month-math tests (fixture: the downloaded May 2026 PDF or a synthetic one) |
| `.github/workflows/collect_tourism.yml` | **Create** - cron monthly (2nd of month 02:30 UTC) + `workflow_dispatch`; pip install pymupdf; `kv_upload.py push tourism` |
| `tools/kv_upload.py` | Modify - register `"tourism": "public/tourism.json"` |
| `src/index.js` (dashboard worker) | Modify - KV route `/tourism.json` → key `tourism` |
| `public/sw.js` | Modify - add `tourism.json` to data-bundle exclusion list; bump `VERSION` |
| `public/index.html` | Modify - SECTIONS entry `tourism`, META, LOADERS/render, i18n EN+MS, prerender shell |
| `tools/prerender_shells.py` | Modify - tourism section shell |
| `README.md` + `public/llms.txt` | Modify - document the data + section (plain hyphens only) |
| `mygov-mcp-worker/src/index.js` | Modify - `mygov_tourism_arrivals` tool (proxy `/tourism.json`) |
| `mygov-mcp/{claude-mygov,codex-mygov}/servers/server.py` + `~/.hermes/mcp-servers/mygov-api-mcp/server.py` | Modify - sync `mygov_tourism_arrivals` (stdlib, custom UA) |

---

## Tasks

### Task 1: Spike - confirm extraction shape on the real PDF

**Objective:** Prove the table extraction works end-to-end and lock the JSON shape before building the collector.

**Files:** (nothing committed - a spike)

**Steps:**
1. Download: `curl -s "https://data.tourism.gov.my/frontend/pdf/2026/visitor_arrivals/top_51_may_2026_visitor.pdf" -o /tmp/tourism_spike.pdf`
2. Extract with pymupdf; print raw text of the page; identify:
   - the header row (rank, country, month 2026/2025/2019, growths, YTD block)
   - where the table body starts/ends (footer/notes after row 51)
   - whether "TOTAL" or "TOTAL FOREIGN" rows exist (they do in the official format)
3. Write a throwaway parser producing `[{rank, country, m2026, m2025, m2019, gm26a (May/Apr), g2025, g2019, ytd26, ytd25, ytd19}]`, print 5 rows + the totals row.
4. **Decision gate:** if rows parse cleanly (51 rows + totals), proceed. If the layout differs (e.g. rotated, multi-line country names), adjust the parser in Task 2 and note the deviation in the plan.

**Verify:** printed rows match the values seen in the raw text (e.g. rank 1 SINGAPORE 1,696,732).

---

### Task 2: `tools/collect_tourism.py` - URL probing + download

**Objective:** Deterministically find and download the latest published month without any login.

**Files:**
- Create: `tools/collect_tourism.py`

**Step 1: Month helpers**
```python
MONTHS = ["jan","feb","mac","apr","mei","jun","jul","ogo","sep","okt","nov","dis"]  # Malay
def month_range(last):  # last = date; yield (year, malay_month, full_name) newest→oldest
    ...
```

**Step 2: Probe newest→oldest**
```python
def find_latest(base_url, year, months_back=3):
    """Probe candidate URLs newest-first until one returns 200.
    Returns (url, year, malay_month) or None."""
    # candidates: 2026-style top_51_{m}_{y}_visitor.pdf, then 2025-style {n}_top_45_..._{full}_{y}.pdf
```
- Try the current year's `visitor_arrivals` pattern for each month from `dis` backwards (or from the current month backwards); first 200 wins.
- If none in the current year, try the previous year's `tourist_arrivals` pattern.
- Use a custom `User-Agent: mygov-tourism/1.0 (+https://mygov.faizalmzain.com)` (the Cloudflare 403-on-default-UA lesson from the flood collector applies here too).
- 3 attempts with 5/10s backoff on transient errors; a 404 is a definitive "not published yet" (no retry).

**Step 3: Download + cache**
- Save to `/tmp` (or `.cache/`), read once, extract, delete. Never commit the PDF.
- Also download the matching `tourist_arrivals` and `excursionist_arrivals` PDFs for the SAME month if present (they complete the picture: visitor = tourist + excursionist).
- **Fallback:** if no PDF found for the current month (mid-month lag), the collector keeps yesterday's `tourism.json` (never writes an empty file - same rule as the insights collector).

**Verify:** `python3 tools/collect_tourism.py --dry-run` prints the resolved URL + month.

---

### Task 3: Table extraction → `public/tourism.json`

**Objective:** Parse the pymupdf text into the JSON the dashboard + MCP consume.

**Files:**
- Modify: `tools/collect_tourism.py`
- Create: `tests/test_tourism.py`

**Step 1: Write failing test** (fixture: `tests/fixtures/visitor_sample.txt` = the first ~2000 chars of the May 2026 extraction, trimmed)
```python
def test_parse_rows():
    from collect_tourism import parse_visitor_table
    rows = parse_visitor_table(open("tests/fixtures/visitor_sample.txt").read())
    assert rows[0]["country"] == "SINGAPORE"
    assert rows[0]["m2026"] == 1696732
    assert len(rows) >= 50
def test_month_number():
    assert malay_to_num("mac") == 3 and malay_to_num("dis") == 12
```

**Step 2: Implement `parse_visitor_table(text)`**
- Split lines; detect the header row (contains "COUNTRY" and "GROWTH"); detect the totals row(s) by "TOTAL"; drop note/footnote lines (short lines, trailing "Source:" etc.).
- Number parsing: strip commas; parentheses `(4.7)` = negative growth; blanks/`-` → None.
- Country names can span two lines in some reports (e.g. "SRI LANKA" wrapped) - merge a line that is a bare country continuation when the next token is a number.
- Columns (month block): rank, country, m2026, m2025, m2019, g_mom, g_2025, g_2019, then YTD block: ytd26, ytd25, ytd19, gy26, gy25, gy19. The 2019 block only exists in newer reports - detect by header presence; older reports have fewer columns (parse per header tokens found).

**Step 3: JSON shape** (the contract for dashboard + MCP)
```json
{
  "generated": "2026-08-11",
  "asOf": {"year": 2026, "month": 5, "label": "May 2026"},
  "totals": {"visitor": 12345678, "tourist": ..., "excursionist": ...},
  "visitor": [ {"rank":1, "country":"SINGAPORE", "m2026":1696732, "m2025":1899217, "m2019":1817885,
                 "g_mom":11.9, "g_2025":4.5, "g_2019":25.4,
                 "ytd26":8737229, "ytd25":8344147, "ytd19":7315074, "gy_2025":4.7, "gy_2019":19.4}, ...],
  "tourist": [...], "excursionist": [...]
}
```
- Numbers are ints/None; growths are floats/None (negative = parenthesised in the PDF).
- `totals` row extracted from the PDF's TOTAL row (not summed client-side - trust the official total).

**Step 4: Run tests** - `python3 -m pytest tests/test_tourism.py -q` → pass.

**Step 5: Run against the live PDF** - full pipeline: `python3 tools/collect_tourism.py` → validate `public/tourism.json` (`len(visitor) >= 50`, totals non-null, SINGAPORE rank 1).

**Step 6: Commit** - `git add tools/collect_tourism.py tests/ && git commit -m "tourism: monthly visitor-arrivals collector (PDF -> JSON)"`

---

### Task 4: GitHub Action `collect_tourism.yml`

**Objective:** Monthly cron + manual dispatch; push to KV.

**Files:**
- Create: `.github/workflows/collect_tourism.yml`

**Content (mirror `collect_insights.yml` patterns):**
```yaml
name: collect-tourism
on:
  schedule:
    - cron: "30 2 2 * *"      # 2nd of each month, 02:30 UTC (data lags ~1 month)
  workflow_dispatch:
permissions: { contents: read }
jobs:
  collect:
    runs-on: ubuntu-latest
    env: { CF_API_TOKEN: ${{ secrets.CF_API_TOKEN }}, CF_ACCOUNT_ID: ${{ secrets.CF_ACCOUNT_ID }} }
    steps:
      - uses: actions/checkout@<sha>          # SHA-pinned like the other workflows
      - uses: actions/setup-python@<sha>
        with: { python-version: "3.12" }
      - run: pip install pymupdf
      - run: python3 -m py_compile tools/collect_tourism.py
      - run: python3 -m pytest tests/test_tourism.py -q
      - run: python3 tools/collect_tourism.py
      - run: python3 - <<'PY'               # validation gate
        # tourism.json must have >=50 visitor rows, totals present, asOf sane
        PY
      - run: python3 tools/kv_upload.py push tourism
```
- No `on: push` catch-up (monthly data doesn't need it).
- The collector itself exits 0 and keeps yesterday's KV value when nothing new is published (empty-write guard in Task 2 Step 3).

**Verify:** `gh workflow run collect_tourism.yml` → `completed success`; `gh run list` shows the run.

---

### Task 5: Dashboard - Tourism section

**Objective:** A compact "Tourism" section showing the latest month's arrivals.

**Files:**
- Modify: `public/index.html`, `tools/prerender_shells.py`

**Step 1: SECTIONS + META**
- Add `{ id:"tourism", label:"Tourism", icon:"globe" (or reuse plane icon), family:"tourism" }` to `SECTIONS` (position: after Population, before Economy - it's a national-scale stat; user can veto placement).
- Add `META.tourism` with title/desc/how (source: data.tourism.gov.my, monthly, attribution line).

**Step 2: Loader + renderer** (follow the established section pattern)
```js
async function loadTourism(){
  const r = await fetch("tourism.json", { cache:"no-store" });
  if (!r.ok) throw new Error("tourism " + r.status);
  return r.json();
}
function renderTourism(d){
  // KPI row: visitors this month (m2026 of totals), y/y growth, YTD total
  // Table: top 10 countries by m2026 with y/y growth chips (compact, tooltips)
  // Note: "Data provided by Tourism Malaysia" attribution
}
```
- Follow the established **compact chip/table** UX (the user's explicit preference): a small table with rank/country/arrivals/growth, sorted by m2026 desc, top 10; the full 51 in a `<details>` disclosure. No charts initially (monthly single-point isn't a chart yet; a YTD bar could come later).
- i18n keys: `"Tourism"`, `"Visitor arrivals"`, `"Tourists"`, `"Excursionists"`, `"Monthly arrivals"`, `"Year to date"`, `"vs May 2025"` etc., both EN + MS.
- Add `tourism.json` to `prerender_shells.py`'s awareness if the section needs a static shell (yes - every section does; add its shell to the generator and re-run it + `node --check`).

**Step 3: sw.js + Worker**
- `public/sw.js`: add `tourism.json` to the exclusion list; bump `VERSION` (v10 → v11).
- `src/index.js`: add `"/tourism.json": { key: "tourism", type: "json" }` to the KV route dict.

**Step 4: Verify in browser** - `wrangler dev` → load section → 10 rows render, BM toggle works, missing KV key degrades to error-box + retry (standard section behaviour), `node --check` passes.

**Step 5: Commit** - `git commit -m "dashboard: Tourism section (monthly visitor arrivals)"`

---

### Task 6: MCP tool `mygov_tourism_arrivals`

**Objective:** Expose the same JSON through the MCP surface on all four servers.

**Files:**
- Modify: `mygov-mcp-worker/src/index.js` (hosted Worker, `mygov-mcp.faizalmzain.com`)
- Modify: `mygov-mcp/claude-mygov/servers/server.py`, `mygov-mcp/codex-mygov/servers/server.py`, `~/.hermes/mcp-servers/mygov-api-mcp/server.py`

**Step 1: Worker tool definition** (mirror `mygov_pricecatcher`):
```js
{
  name: "mygov_tourism_arrivals",
  description: "Latest monthly international visitor arrivals to Malaysia (top 51 countries, tourism.gov.my). "
    + "Filters: country (case-insensitive substring), min_rank. Returns arrivals, y/y growth, YTD. Monthly data.",
  inputSchema: { type:"object", properties: {
      country: { type:"string", description:"country name substring, e.g. SINGAPORE, CHINA" },
      min_rank: { type:"number", description:"only ranks <= this (default 51)" } },
    required: [] },
  readOnlyHint: true, openWorldHint: false, destructiveHint: false
}
```
- Dispatch: fetch `https://mygov.faizalmzain.com/tourism.json?cb=${t}` (same-origin KV-backed, like `mygov_flood_risk`), filter + shape, TTL 3600 (monthly data - long cache fine).

**Step 2: Python stdio** - `get_tourism_arrivals(country, min_rank)` with `urllib.request` + custom UA (`mygov-mcp/1.0 (+https://mygov.faizalmzain.com)` - the Cloudflare 403 lesson), TOOLS entry, dispatch branch. Sync all three copies.

**Step 3: Validate + deploy**
- `claude plugin validate ./claude-mygov --strict` → passes.
- Deploy Worker; `tools/list` shows 10 tools.
- Live test: `mygov_tourism_arrivals` with no filter → 51 rows, SINGAPORE rank 1; `country:"china"` → CHINA row.

**Step 4: Commit** - `git commit -m "mcp: mygov_tourism_arrivals tool (monthly arrivals)"` on the mygov-mcp repo.

---

### Task 7: README, llms.txt, skill update

**Objective:** Document everything; keep the repo's docs convention (plain hyphens only).

**Files:** `README.md`, `public/llms.txt`, and the `mygov-dashboard` skill.

**Steps:**
1. README: Tourism section row in the table + a "Tourism data" paragraph: source (data.tourism.gov.my monthly PDFs), cadence (monthly), attribution requirement, extraction note (pymupdf, no login needed), the Malay-month URL pattern gotcha (`mac` not `mar`).
2. `llms.txt`: add `tourism.json` + one line describing the section.
3. Skill (`mygov-dashboard`): a **tourism** bullet - the public-PDFs discovery (login reveals index, files are open), the two URL patterns, Malay month abbreviations, the `Top_51` capital-T excursionist filename, pymupdf extraction, KV key `tourism`, MCP tool name, and the ToU/attribution note.
4. Verify `grep -c "-\|-" README.md` → 0.

---

## Deployment & end-to-end verification

1. Push all repos → auto-deploy (~40-90s).
2. Seed KV once: `npx wrangler kv key put tourism --namespace-id=40812fc5fedb4e1fb66d70f75e707f90 --path=public/tourism.json --remote`.
3. Fire the workflow: `gh workflow run collect_tourism.yml` → `completed success`.
4. `curl "https://mygov.faizalmzain.com/tourism.json?cb=$(date +%s)"` → real JSON, 51+ rows.
5. Browser: Tourism section renders (nav item present, 10-row table, BM toggle).
6. MCP: `curl -s "https://mygov-mcp.faizalmzain.com/mcp"` tools/list contains `mygov_tourism_arrivals`; live call returns SINGAPORE rank 1.

## Risks & tradeoffs

- **PDF layout drift** - Tourism Malaysia reformats the PDFs occasionally (2019 columns appear/disappear; two-line country names). Mitigation: header-token-driven column detection + tests + the collector refuses to write when rows < 50 (keeps yesterday's data). Worst case = stale tourism data, not a broken site.
- **Month-lag** - data is published ~1 month behind (May published in July). The dashboard should label `asOf` clearly ("May 2026").
- **No login dependency** - by design: files are public; pattern-probing avoids ever storing the user's session cookie in CI. If the URL scheme changes, the collector falls back to probing older patterns; the login index (user-run) is the manual recovery path.
- **KV budget** - 1 write/month: negligible.
- **Attribution/ToU** - dashboard + MCP both display "Data provided by Tourism Malaysia". Non-commercial only; no AI-training use of the raw text (no LLM in the pipeline by design).
- **MCP repo separation** - the tool lives in `mygov-mcp` (separate repo), the collector in `mygov` (dashboard repo); no cross-repo commit churn.

## Open questions (defaults chosen, user can veto)

1. **Section placement** - after Population, before Economy (default). Alternative: inside Economy as a sub-block.
2. **Table depth** - top 10 visible + all 51 in `<details>` (default, per compact-UX preference). Alternative: top 20 visible.
3. **Charts** - none initially (default); a YTD bar chart could be added once 2+ months accumulate.
4. **Excursionist/tourist split** - parse all three PDFs (visitor/tourist/excursionist) into separate arrays (default, they're one extra fetch). Alternative: visitor-only for v1.
5. **Archive backfill** - not in scope (default); the 2014-2025 archive stays unexplored unless the user wants a historical chart.
