# AI Insights + Forecasts for mygov Dashboard - Implementation Plan (rev 2)

> **For Hermes:** Use subagent-driven-development skill to implement this plan task-by-task.
>
> **Revision note (2026-08-11).** Rev 1 was reviewed against the live data before
> implementation started. The architecture survived unchanged. The *forecast
> targets* did not: three of the four series it picked are administered prices
> and the fourth is a random walk. Rev 2 keeps the pipeline, swaps the targets
> for series that are measurably predictable, adds the numeric grounding gate
> that rev 1 was missing, and defers the heavy dependency. Sections marked
> **[rev 2]** are the changed ones; everything else stands.

**Goal:** Give every mygov visitor AI-assisted data presentation (a bilingual daily "Today in Malaysia" briefing) and honest short-horizon forecasts, served from the existing collectors -> KV -> Worker pipeline at $0 runtime cost, working in every browser (no model downloads).

**Architecture (unchanged):** Two new KV-served JSON files, generated entirely in CI:
- `insights.json` - LLM-written (Gemini flash, already proven in `collect_radar.py`) daily briefing in EN+MS, grounded in that day's real data **and in statistically detected anomalies**.
- `forecasts.json` - statistically computed, with prediction intervals. **Rule: statistics for numbers, LLM for words.**

Both ride the pipeline that already works five times over: GitHub Actions cron -> collector script -> `kv_upload.py push` -> KV (`MYGOV_DATA`) -> Worker routes -> app loaders. No runtime AI calls, no per-visitor cost, works offline, PWA-cacheable.

---

## [rev 2] What is actually forecastable - measured, not assumed

Everything below was measured on the repo's own committed data on 2026-08-11.
Re-run these checks if the data shape changes; do not take them on faith.

### Rejected targets and why

| Series | Finding | Verdict |
|---|---|---|
| **RON95** | Last 104 weeks: 26 distinct values, price changed in only 29 of them, **min 2.05 / max 4.27**. That range is the subsidy peg giving way to a float - a policy regime break, not a stochastic process. | **Drop.** ETS across a regime change produces an artefact, not a forecast. |
| **RON97 / diesel** | Move more freely (60 and 67 changes in 104 weeks) but are still ceilings set weekly by MOF. | **Drop.** A committee decision is not a time series. |
| **USD/MYR** | One-step-ahead MAE over the last 250 obs: naive (`tomorrow = today`) **0.00991**, drift model **0.01022**. Extrapolation is *worse than the flat line*. | **Drop.** Textbook random walk, reproduced on our data. Also edges toward financial advice on a public dashboard. |
| **CPI** | Monthly, ~6-week publication lag, ~24 usable points for a 4-month horizon. | **Drop.** Weak, and "predicted inflation" is the number most likely to be screenshotted out of context. |
| **Rice (BERAS SUPER)** | Price-controlled item. | **Drop.** Same objection as fuel. |

### Accepted targets and why

Does knowing *last week's same weekday* beat knowing *yesterday*? (MAE, last 200 obs)

| Series | naive | seasonal-naive (7d) | gain |
|---|---|---|---|
| **Shuttle Tebrau ridership** | 712 | 324 | **+54.5%** |
| **Blood donations (all)** | 731 | 381 | **+47.9%** |
| Blood donations, AB | 41 | 29 | +29.5% |
| Komuter ridership | 5,076 | 4,258 | +16.1% |
| Komuter Utara ridership | 2,603 | 2,267 | +12.9% |
| _ETS rail_ | 2,308 | 2,428 | _-5.2%_ |
| _Intercity_ | 698 | 795 | _-13.9%_ |
| _FPX value_ | 482m | 637m | _-32.2%_ |

Human-routine count series carry real weekly structure. Ship forecasts only for
the rows above the line, and **only where the backtest gain is positive** -
compute the gain at collect time and skip any series that fails (see Task 3).

Two notes for the implementer:
- **FPX is not disproven, it is mis-probed.** A 7-day lag is the wrong test for
  a series driven by month-end and payday. If you want FPX, model a monthly
  term; do not ship it on the strength of the weekly test failing.
- **Holidays are already available** as a regressor: `slow.json -> holidays`
  is `[[YYYY-MM-DD, name, major], ...]`, 146 entries from 2021. Chinese New Year
  and Ramadan are exactly the effects a seasonal model must be told about - the
  Feb 2026 Komuter spike is CNY (17 Feb) and the level shift after it is Ramadan
  (19 Feb). A seasonal-naive that ignores them will read the holiday as an
  anomaly every single year.

---

## Design decisions (with rationale)

| Decision | Choice | Why |
|---|---|---|
| AI runs in CI, not runtime | CI (collector) | Zero cost, cached, offline; runtime AI rejected after research - Chrome APIs need model downloads, `window.ai` absent in user's build, Translator lacks en<->ms |
| Two files, one collector script | `collect_insights.py` writes both keys | One workflow, one Gemini call/day, shared data loading |
| **[rev 2] Forecast targets** | Ridership (per service) + blood donations | The only series where seasonality measurably beats naive; see the table above |
| **[rev 2] Forecast method** | Seasonal-naive + empirical quantile bands, holiday-aware | Beats naive by 13-55% on the accepted series. `statsforecast` (numba + scipy + llvmlite) is a slow, fragile CI install for gains a backtest has not yet demonstrated - defer it until one does |
| **[rev 2] Forecast horizon** | 14 days | Two full weekly cycles; long enough to be useful, short enough that the band stays honest |
| **[rev 2] Numeric grounding gate** | Every numeral in LLM output must appear in the facts JSON, else the bullet is dropped | The one control that makes LLM prose publishable next to a `.gov.my` attribution. A prompt instruction is a hope, not a control |
| **[rev 2] Detect, then narrate** | Seasonal decomposition flags residuals > 2.5 sigma; only flagged events reach the prompt | Turns "RON95 is 3.77" into "donations are 20% below normal for a Tuesday". Quiet days produce a short brief instead of filler |
| Brief language | Gemini writes both `t_en` and `t_ms` in one call | No client translation; Malay translation API unavailable |
| Brief bullets | 4-5 max, each tagged with a target section id | Bullets link into existing sections, like KPI cards |
| Dashboard placement | Compact "AI Insights" band under the hero KPI strip, not a nav section | Nav stays at 11; no SECTIONS/LAZY/prerender surgery |
| **[rev 2] Forecast UI** | Dashed extension + shaded band on the ridership and blood-donation charts | Both already exist and already carry holiday markers, so the forecast lands in context |
| Graceful degradation | Band hidden when `insights.json` missing/stale; forecast overlay hidden when absent | Never blocks core data |
| **[rev 2] Chart narration as a11y** | One generated sentence per chart, cached on a hash of the series, used as `aria-describedby` | A chart-heavy page currently gives screen-reader users a bare canvas. Same generation pass, real accessibility win, also feeds the SEO snapshot |

**Explicitly out of scope (YAGNI):** `/api/ask` chat endpoint; flood "prediction" (weather-dependent, would be noise); bus/train arrival prediction (already live data); **[rev 2]** any forecast of a price set by government.

---

## Files to change

| File | Change |
|---|---|
| `tools/collect_insights.py` | **Create** - loads slow.json + health.json + prices.json + radar.json, detects anomalies, computes forecasts, builds the grounded Gemini prompt, writes `public/insights.json` + `public/forecasts.json` |
| `tests/test_forecast.py` | **Create** - backtest + band ordering + **grounding gate** tests (pytest; repo has no test dir yet) |
| `.github/workflows/collect_insights.yml` | **Create** - cron 01:30 UTC (after radar at 01:00), `workflow_dispatch`, **pandas only**, runs collector, `kv_upload.py push insights forecasts` |
| `tools/kv_upload.py` | Modify - add `insights` / `forecasts` to `FILES` |
| `src/index.js` | Modify - add both paths to the KV-route dict |
| `public/sw.js` | Modify - add both to the data-bundle exclusion list; bump `VERSION` |
| `public/index.html` | Modify - AI band markup + loaders/renderers, forecast overlay in `paintRid` and the blood-donation painter, `aria-describedby` wiring, i18n (EN+MS) |
| `tools/prerender_shells.py` | Modify - static shell for the AI band (CLS) |
| `README.md` | Modify - document the new data files (plain hyphens only) |
| `public/llms.txt` | Modify - mention the AI band + data files |

---

## Tasks

### Task 1: Add `insights` + `forecasts` keys to kv_upload.py

Unchanged from rev 1. Add both to the `FILES` dict; confirm they appear in the
usage text. Note the scoped-push contract: the workflow must call
`kv_upload.py push insights forecasts`, never a bare `push`, or it will
re-upload the git-committed copies of the other collectors' files over fresher
KV values.

**Verify:** usage output lists both keys.

---

### Task 2: [rev 2] `forecast_series` - seasonal-naive with empirical bands

**Objective:** A forecast function that is honest about its own accuracy, with
no heavy dependency.

**Files:** Create `tools/collect_insights.py`, `tests/test_forecast.py`

**Step 1: Write failing tests**

```python
# tests/test_forecast.py
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "tools"))
from collect_insights import forecast_series, backtest_gain, ground

def test_bands_ordered_and_sized():
    hist = [100 + (i % 7) * 10 for i in range(120)]      # pure weekly cycle
    out = forecast_series(hist, horizon=14, season=7)
    assert len(out) == 14
    for r in out:
        assert r["lo"] <= r["mid"] <= r["hi"]
    # a perfectly periodic series should forecast itself with a tight band
    assert out[0]["mid"] == hist[-7]
    assert out[0]["hi"] - out[0]["lo"] < 1.0

def test_backtest_gain_detects_seasonality():
    seasonal = [100 + (i % 7) * 10 for i in range(200)]
    assert backtest_gain(seasonal, season=7) > 0.5      # weekly lag wins big
    trend = [float(i) for i in range(200)]              # no weekly structure
    assert backtest_gain(trend, season=7) <= 0

def test_short_series_returns_nothing():
    assert forecast_series([1.0, 2.0, 3.0], horizon=14, season=7) == []

def test_grounding_rejects_invented_numbers():
    facts = {"ron95": 3.77, "donations": 1657}
    assert ground("RON95 is RM3.77 this week", facts) is True
    assert ground("Donations hit 1657 today", facts) is True
    assert ground("Inflation rose to 4.2%", facts) is False   # 4.2 not in facts
```

**Step 2:** Run -> FAIL (module missing).

**Step 3: Implement.** Keep it flat and dependency-free (stdlib + the pandas
already installed for other collectors; no `statsforecast`).

```python
def backtest_gain(hist, season=7):
    """Fractional MAE improvement of seasonal-naive over naive, in-sample.
    <= 0 means the weekly lag carries no information: do not ship a forecast."""
    if len(hist) < season * 8:
        return 0.0
    naive  = [abs(hist[i + 1] - hist[i])      for i in range(len(hist) - 1)]
    snaive = [abs(hist[i + season] - hist[i]) for i in range(len(hist) - season)]
    mn = sum(naive) / len(naive)
    ms = sum(snaive) / len(snaive)
    return 0.0 if mn == 0 else (mn - ms) / mn


def forecast_series(hist, horizon=14, season=7, holidays=None):
    """Seasonal-naive point forecast with empirical prediction intervals.

    Point forecast = the value `season` steps back (carried forward for
    horizons beyond one cycle). The band is the empirical 10th/90th percentile
    of that estimator's own historical residuals - so it reports the accuracy
    the method actually achieved on this series rather than a distributional
    assumption. Returns [] when the series is too short to justify one.
    """
    if len(hist) < season * 8:
        return []
    resid = sorted(hist[i + season] - hist[i] for i in range(len(hist) - season))
    lo_q = resid[int(0.10 * len(resid))]
    hi_q = resid[int(0.90 * len(resid))]
    out = []
    for i in range(horizon):
        base = hist[-season + (i % season)]
        out.append({"mid": round(base, 2),
                    "lo":  round(base + lo_q, 2),
                    "hi":  round(base + hi_q, 2)})
    return out
```

**Holiday handling (required, not optional).** Before fitting, replace values on
`major` holidays with the median of the surrounding non-holiday window, and mark
forecast days that fall on a coming holiday as `{"holiday": name}` with a widened
band. Without this the model reads Chinese New Year as a 20-sigma anomaly every
year, and forecasts the week *after* CNY from CNY itself.

**Step 4:** Tests pass. **Step 5:** Commit.

---

### Task 3: [rev 2] `forecasts.json` writer - ridership + blood donations

**Objective:** Forecast only what passes its own backtest.

**Input shapes** (verify against the live files before coding; the loaders in
`index.html` are the source of truth):
- `slow.json -> mobility.rid` = `{t0, n, keys, series:{ets:[...], komuter:[...], ...}}` (dense daily arrays)
- `slow.json -> holidays` = `[[date, name, major], ...]`
- `health.json -> don` = same dense-daily shape, blood donations by type

```python
def build_forecasts(slow, health):
    hol = slow.get("holidays") or []
    fc = {"generated": dt.date.today().isoformat(), "ridership": {}, "blood": {}}
    for bucket, src in (("ridership", slow["mobility"]["rid"]),
                        ("blood", health.get("don") or {})):
        for key in src.get("keys", []):
            hist = [v for v in src["series"][key] if v is not None]
            gain = backtest_gain(hist, 7)
            if gain <= 0.05:                      # 5% floor: no gain, no forecast
                sys.stderr.write(f"  skip {bucket}/{key}: gain {gain:+.1%}\n")
                continue
            f = forecast_series(hist, 14, 7, hol)
            if f:
                fc[bucket][key] = {"gain": round(gain, 3), "t0": src["t0"],
                                   "n": src["n"], "fc": f}
    return fc
```

Three rules for the implementer:

1. **Do not copy history into `forecasts.json`.** Rev 1 embedded `hist` arrays,
   duplicating data already in `slow.json` / `health.json` and creating two
   copies that can disagree. Ship `t0`/`n` so the client can align the forecast
   to the series it already loaded.
2. **Ship the backtest gain.** The UI should be able to say how much better than
   guessing this is, and a reviewer should be able to see a forecast quietly
   degrade.
3. **Sanity gate before write** (mirror `collect_prices.py`): if *no* series
   qualifies, refuse to write the file rather than publishing an empty one.

**Verify:** `ridership.shuttle_tebrau` and `blood.all` present with `gain` around
`+0.55` and `+0.48`; `ets` and `intercity` absent (negative gain); all bands
ordered `lo <= mid <= hi`.

---

### Task 4: [rev 2] Anomaly detection - the input the brief actually needs

**Objective:** Find what changed before asking an LLM to describe it.

```python
def anomalies(series_map, holidays, z=2.5):
    """Residual outliers against the weekly seasonal norm, holidays excluded.
    Returns [{"key","date","value","expected","z","dir"}...] sorted by |z|."""
```

For each daily series: compute the seasonal-naive residual, its rolling standard
deviation, and flag `|residual| > z * sd`. **Exclude major holidays** - they are
explained, not anomalous, and `slow.json -> holidays` already says which days
those are.

Typical output is 3-8 events a day. This, not the raw current values, is what
makes the brief worth reading: it is the difference between restating the KPI
tiles and telling the reader something they could not see.

**Verify:** run over the stored history and confirm the Feb 2026 Komuter spike is
**not** flagged (CNY is in the holiday table), while a genuine unexplained
movement is.

---

### Task 5: [rev 2] Gemini brief - grounded, with a hard numeric gate

Prompt contract as rev 1 (temperature 0.2, strict JSON, fence stripping,
balanced-brace rescue - copy the proven pattern from `collect_radar.py`), with
two changes:

- The prompt receives **`anomalies` + today's headline facts + the forecast
  summary**, not a raw value dump.
- Rules add: *use only numbers present in the supplied facts.*

**Then enforce it in code, because the prompt cannot:**

```python
def ground(text, facts):
    """True if every numeral in `text` appears in `facts`.
    A prompt saying "do not invent data" is a hope; this is the control.
    Without it we eventually publish a hallucinated figure under a .gov.my
    attribution, which is not a recoverable error for this project."""
    allowed = set()
    for v in facts.values():
        if isinstance(v, (int, float)):
            allowed.update({f"{v}", f"{v:.1f}", f"{v:.2f}", f"{round(v)}"})
    for tok in re.findall(r"\d+(?:[.,]\d+)?", text):
        if tok.replace(",", "") not in allowed:
            return False
    return True
```

Drop any bullet that fails `ground()`, in both languages, and log the rejection.
If every bullet fails, write `bullets: []` - the band hides and the site is
unaffected.

**Resilience (unchanged):** no `GOOGLE_API_KEY` -> empty bullets, exit 0, never
fail the workflow. `--brief-only` / `--forecasts-only` flags.

**Verify:** every numeral in every rendered bullet appears in the facts JSON;
deliberately corrupt one model output in a test and confirm the bullet is dropped.

---

### Task 6: GitHub Action

As rev 1, with `pip install pandas` only (no `statsforecast` - see Task 2).
Cron 01:30 UTC, `workflow_dispatch`, scoped push. No `on: push`.

---

### Task 7: Worker routes + sw.js exclusion

Unchanged from rev 1. Add `/insights.json` and `/forecasts.json` to the KV-route
dict in `src/index.js`; add both to the data-bundle exclusion list in
`public/sw.js` and bump `VERSION`.

> Note: `VERSION` is at **v10** as of 2026-08-11 (rev 1 said v9). Bump from
> whatever is current, do not hardcode v10.

---

### Task 8: [rev 2] Dashboard - AI band, forecast overlay, chart narration

**Band:** as rev 1 - compact, under the hero KPI strip, static shell in
`prerender_shells.py` for CLS, hidden when bullets are empty.

> `prerender_shells.py` splices are re-entrant as of 2026-08-11, so the band's
> shell will regenerate correctly on re-runs. Match the existing splice style.

**Forecast overlay** (replaces rev 1's FX/fuel/CPI/grocery sparklines): extend
the **ridership** and **blood-donation** line charts with a dashed continuation
and a shaded `lo`/`hi` band. Both charts already carry the holiday markers, so
the forecast lands in the context that explains it. Label it
`forecast - 80% band` and show the backtest gain in the tooltip.

**Chart narration:** one generated sentence per chart, wired as
`aria-describedby` on the canvas, cached on a hash of the underlying series so it
regenerates only when the data moves.

---

### Task 9: README + llms.txt

Document `insights.json` / `forecasts.json`, the grounding gate, and - important
for anyone reading the numbers - **which series are forecast and which are
deliberately not, and why**. Plain hyphens only; verify with
`grep -c "—\|–" README.md` -> 0.

---

## Deployment & verification (end-to-end)

1. `git push` -> auto-deploy (~40-90s).
2. `gh workflow run collect_insights.yml` -> `gh run list` -> `completed success`.
3. `curl "https://mygov.faizalmzain.com/forecasts.json?cb=$(date +%s)"` -> real JSON.
4. Browser: band visible, BM works, forecast overlay on both charts, no console errors.
5. **Grounding spot-check:** every numeral in every bullet appears in that day's data.
6. Lighthouse: perf stays >= 95.

## Risks & tradeoffs

- **A forecast is not a promise.** Every forecast UI carries `forecast - 80% band`
  labelling and the measured backtest gain. Seasonal-naive projects routine; it
  cannot see a strike, a flood, or a policy change.
- **[rev 2] Reintroducing rejected targets.** If someone later asks for an FX or
  fuel forecast, re-run the backtest in the table above first. The measurement,
  not the request, decides.
- **Gemini output drift** - strict JSON + rescue parse + **grounding gate** +
  empty-bullets fallback. Worst case is no band, not a wrong number.
- **[rev 2] Anomaly false positives** - holidays are excluded via the holiday
  table; keep the z threshold at 2.5 and prefer missing an event to inventing one.
- **KV write budget** - 2 extra writes/day against 1,000/day: negligible.
- **Chrome built-in AI stays rejected** (researched 2026-08-11) - do not
  resurrect client-side AI without re-verifying availability.

## Locked decisions

1. **Band placement: under the hero KPI strip**, not a nav section. (rev 1, stands)
2. **[rev 2] Horizon: 14 days** on daily count series - two weekly cycles.
   Supersedes rev 1's "7-day FX/fuel, 4-week CPI/rice", whose targets are gone.
3. **[rev 2] Forecast only what beats naive by >= 5%**, measured at collect time
   and shipped alongside the number. Supersedes rev 1's fixed target list.
4. **Brief tone: factual-neutral.** A government-data dashboard states, it does
   not speculate. (rev 1, stands)
5. **Bilingual: Gemini writes both languages in one call.** (rev 1, stands)
6. **[rev 2] No LLM-authored numerals reach the page.** Statistics produce every
   number; the model only phrases them; `ground()` enforces it.
