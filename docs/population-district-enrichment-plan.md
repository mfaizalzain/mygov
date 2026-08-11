# Enrich Population Section: Sex + Ethnicity + Income by District

> **For Hermes:** Use subagent-driven-development skill to implement this plan task-by-task.

**Goal:** Enrich the dashboard's Population → Places view with sex, ethnicity, **income, poverty and inequality** at the **district** level (currently state-level only for composition; constituency-level only for socioeconomics).

**Architecture:** Two verified sources:
1. DOSM `population_district.parquet` (already fetched weekly by `tools/collect_geo.py`) carries full sex × ethnicity × age for all 164 districts — `build_district()` currently keeps only overall population + YoY growth.
2. OpenAPI district socioeconomic datasets (NOT currently collected): `hh_income_district`, `hh_poverty_district`, `hh_inequality_district` — 172 districts, 2019/2022/2024 releases.

**Tech Stack:** Python (collect_geo.py), Cloudflare KV (geo key), vanilla JS (public/index.html), Chart.js.

---

## Data verified (2026-08-11)

**A. Demographics — `https://storage.dosm.gov.my/population/population_district.parquet`**
- 383,040 rows; cols `state, district, date, sex, age, ethnicity, population`
- Ethnicities: `bumi_malay, bumi_other, chinese, indian, other_citizen, other_noncitizen`
- Sexes: `both, male, female`; 18 age bands; 164 districts; latest 2026

**B. Socioeconomics — OpenAPI (verified live):**
| Dataset | Fields | Coverage |
|---|---|---|
| `hh_income_district` | `income_mean`, `income_median` | 172 districts, 2019/2022/2024 |
| `hh_poverty_district` | `poverty_absolute`, `poverty_relative` | 172 districts, same years |
| `hh_inequality_district` | `gini` | 172 districts, same years |

## Payload impact (verified)

| Addition | JSON size | vs current geo.json (158 KB) |
|---|---|---|
| Ethnicity per district (6 groups) | +20.5 KB | +13% |
| + Sex split (male/female) | +30 KB total | +19% |
| + Income/poverty/gini per district | ~+10 KB | ~+6% |
| **Total** | **~+40 KB** | **~+25% → ~198 KB** |

Age bands stay state-level (already charted there; +90 KB district-level is too heavy for a table).

## Data shape change to geo.json

Current `district.list` row: `{"n": "Petaling", "s": "Selangor", "p": 2370.6, "g": 0.46}`

New row: `{"n", "s", "p", "g", "eth": {"bumi_malay": ..}, "sx": {"male": .., "female": ..}, "inc": 6504, "pov": 2.9, "gini": 0.338}`
- `p`/`g` in thousands as published; `eth`/`sx` in thousands; `inc` in RM (raw); `pov` in %; `gini` 0–1
- Socio keys join on (state, district) from the newest release year (2024); omitted when absent
- Missing rows → omit key (4 districts lack newest population year; socio covers 172 districts)

## Task list (bite-sized)

### Task 1: Extend build_district() in collect_geo.py — demographics
- From the already-fetched `population_district.parquet`:
  - `eth`: `sex == "both" & age == "overall"` rows, ethnicity != "overall"
  - `sx`: `age == "overall" & ethnicity == "overall"` rows, sex in (male, female)
- Same `latest` year as `p`/`g`; round 1 decimal; omit key when row missing
- Unit tests: pure-function extraction test with a small mock DataFrame
- Run + verify geo.json; commit

### Task 2: Add district socioeconomic to collect_geo.py — income/poverty/gini
- New `build_district_socio()`: fetch `hh_income_district`, `hh_poverty_district`, `hh_inequality_district` (OpenAPI, same 4/min limiter + sleep pattern as `build_socio`)
- Join on (state, district) newest release; attach `inc` (median), `pov` (absolute), `gini` to matching `district.list` rows
- Unit tests: pure join function
- Run + verify; commit

### Task 3: Enrich district table UI — top group + income columns
- `placesDistRows(g)`: pass through `eth`, `inc`, `pov`, `gini`
- `paintPlacesDistricts`: add columns — Top group (`Malay · 57%`, reuse `ethnicLabel()`), Median income (`RM 6,504`, `nf()`), Poverty (`2.9%`), Gini (`0.338`)
- Headers sortable; i18n EN+MS: "Top group", "Median income", "Poverty", "Gini"
- Verify in browser: Petaling shows Malay majority + income; BM switch; sort works
- Commit

### Task 4: KV + deploy + docs
- geo.json rides the existing `geo` KV key + weekly workflow — no workflow change; re-run collector + push
- README: Population section gains district ethnicity/sex/income/poverty/gini
- Update `mygov-dashboard` skill
- Commit + deploy + verify live (curl geo.json; browser district table)

## Verification
- `python3 tools/collect_geo.py` → districts have eth+sx+inc+pov+gini; ~198 KB
- `python3 -m pytest tests/ -q` → all pass
- Local wrangler dev + browser: district table shows all new columns; search/sort intact
- Live after deploy: curl geo.json; table renders; Lighthouse unchanged

## Risks / notes
- Socio joins on (state, district) labels — must match exactly (`W.P. Kuala Lumpur` vs `Kuala Lumpur`); normalize or map if mismatch
- 4 districts lack newest population year; socio covers 172 → columns may show "—" for missing cells
- geo.json +25% (~198 KB) — KV edge-cached, one fetch per session; acceptable (Population is once-per-visit)
- Do NOT add district age bands (+90 KB) — state-level age chart already exists
- Income is RM median (raw), not thousands — keep units distinct in UI labels
