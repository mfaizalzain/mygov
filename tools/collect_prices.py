#!/usr/bin/env python3
"""PriceCatcher collector: grocery basket index for the mygov dashboard.

KPDN enumerators record the shelf price of ~340 items at ~2,100 premises
across all 177 districts, every day. It is the only dataset in the catalogue
that measures the actual grocery bill rather than an index of one, and it
pairs with the fuel prices and CPI the dashboard already shows.

  Source : https://storage.data.gov.my/pricecatcher/pricecatcher_YYYY-MM.parquet
           + lookup_item.parquet (item name/unit/group)
           + lookup_premise.parquet (premise name/type/state/district)
  Writes : public/prices.json  (uploaded to KV by the GitHub Action)

Why a collector and not a browser fetch: PriceCatcher carries
`exclude_openapi: true`, so it is NOT served by api.data.gov.my at all -
`?id=pricecatcher` returns 404. It exists only as monthly Parquet on
storage.data.gov.my, ~2.5 MB per month and 1.8 million rows for July 2026
alone. Aggregating in CI turns 33 MB of Parquet into ~150 KB of JSON and
costs the visitor nothing against the 4-requests-per-minute API limit.

Two different indices, because they answer two different questions
-------------------------------------------------------------------
Both are computed over a *fixed* item basket. This matters more than it
looks: the set of items sampled drifts month to month and district to
district, so an index over "whatever was recorded" measures the sampling,
not the prices. Every number below is restricted to items observed in every
month of the window.

1. Over time (`basket.national`, `basket.states`) - a **Jevons index**: the
   geometric mean of each item's price relative to the base month. This is
   the standard elementary-aggregate formula used when expenditure weights
   are unavailable, which they are here (DOSM does not publish per-item CPI
   weights at this granularity). Equal-weighted by construction; the
   docstring in the payload says so, and the UI should too.

2. Across places (`districts[].idx`) - a **spatial price level**: for each
   item, the district's median divided by the national median, then the
   geometric mean of those ratios. 100 = the national average basket. A
   plain sum of local prices would instead rank districts by which items
   they happen to stock.

`cheapest` uses the same relative-price trick per premise rather than a raw
basket total, for exactly the same reason: a shop carrying only the cheap
half of the basket must not be reported as the cheapest shop in town. A
premise needs MIN_PREMISE_ITEMS of the basket before it is ranked at all.

Run:  python3 tools/collect_prices.py [--months 13]
Deps: pandas, pyarrow (installed by the workflow; the other collectors are
      stdlib-only, but no stdlib module reads Parquet).
"""
import argparse
import datetime as dt
import io
import json
import sys
import time
import urllib.error
import urllib.request

import pandas as pd

BASE = "https://storage.data.gov.my/pricecatcher/"
OUT = "public/prices.json"

WINDOW_MONTHS = 13          # 12 months of change + the base month, so YoY works
MIN_DISTRICT_COVERAGE = 0.5  # basket items must appear in >=half the districts
MIN_PREMISE_ITEMS = 15       # premises below this are not ranked in `cheapest`
MIN_DISTRICT_ITEMS = 30      # districts below this get no spatial index
TOP_PREMISES = 3             # cheapest premises listed per district
# Per-item district ranking (`itemGeo`). A district median for a *single* item
# can rest on one or two enumerator visits, which is noise rather than a price
# level - require a floor before the district is ranked for that item at all.
MIN_ITEM_DISTRICT_OBS = 5
TOP_ITEM_DISTRICTS = 5       # cheapest/dearest districts listed per item
OUTLIER_LO, OUTLIER_HI = 0.2, 5.0   # keep prices within [0.2x, 5x] item median

# Premise types that sell groceries. Prepared-food outlets (Restoran *,
# Medan Selera, Foodcourt) price cooked dishes, which belong to a different
# basket than a kilo of onions - mixing them makes the index meaningless.
GROCERY_TYPES = {
    "Pasar Mini", "Pasar Raya / Supermarket", "Kedai Runcit",
    "Pasar Basah", "Pasar Basah ", "Hypermarket", "Borong", "Kedai Serbaneka",
}
# Belt and braces: the same exclusion expressed on the item side.
EXCLUDE_ITEM_GROUPS = {"MAKANAN SIAP MASAK"}


def fetch(url, optional=False):
    """GET with the same 4-attempt / 5s-10s-15s backoff the other collectors
    use. A transient failure in unattended CI must not cost a day of data."""
    last = None
    for attempt in range(4):
        try:
            req = urllib.request.Request(url, headers={"Accept": "*/*"})
            with urllib.request.urlopen(req, timeout=180) as r:
                return r.read()
        except urllib.error.HTTPError as e:
            if e.code == 404 and optional:
                return None          # month not published yet - not an error
            last = e
        except Exception as e:
            last = e
        sys.stderr.write(f"  attempt {attempt + 1}/4 failed for {url[-42:]}: {last}\n")
        if attempt < 3:
            time.sleep(5 * (attempt + 1))
    if optional:
        return None
    raise last or RuntimeError(f"fetch failed for {url}")


def parquet(url, optional=False):
    raw = fetch(url, optional=optional)
    return None if raw is None else pd.read_parquet(io.BytesIO(raw))


def month_keys(n):
    """The n most recent YYYY-MM keys, oldest first, ending this month."""
    today = dt.date.today()
    keys, y, m = [], today.year, today.month
    for _ in range(n):
        keys.append(f"{y:04d}-{m:02d}")
        m -= 1
        if m == 0:
            y, m = y - 1, 12
    return list(reversed(keys))


def geomean(s):
    """Geometric mean of a positive series, via logs (no overflow on 300+
    factors). Returns None rather than nan so it serialises as JSON null."""
    s = s[s > 0]
    if s.empty:
        return None
    import math
    return math.exp(s.apply(math.log).mean())


def r(x, nd=2):
    """Round for the wire, mapping nan/None to null."""
    if x is None or pd.isna(x):
        return None
    return round(float(x), nd)


def load(months):
    """Download the monthly files + lookups, join, clean. Returns
    (observations dataframe, item lookup, premise lookup, months present)."""
    sys.stderr.write("fetching lookups\n")
    items = parquet(BASE + "lookup_item.parquet")
    premises = parquet(BASE + "lookup_premise.parquet")
    items = items[items.item_code > 0].copy()
    premises = premises[premises.premise_code > 0].copy()
    premises = premises.dropna(subset=["state", "district"])

    grocery = premises[premises.premise_type.isin(GROCERY_TYPES)]
    keep_items = items[~items.item_group.isin(EXCLUDE_ITEM_GROUPS)]

    frames, present = [], []
    for ym in months:
        raw = parquet(f"{BASE}pricecatcher_{ym}.parquet", optional=True)
        if raw is None or raw.empty:
            sys.stderr.write(f"  {ym}: not published, skipping\n")
            continue
        d = raw[raw.price > 0][["date", "premise_code", "item_code", "price"]]
        d = d.merge(grocery[["premise_code", "state", "district"]],
                    on="premise_code", how="inner")
        d = d[d.item_code.isin(keep_items.item_code)]
        d["ym"] = ym
        frames.append(d)
        present.append(ym)
        sys.stderr.write(f"  {ym}: {len(d):>9,} obs  "
                         f"{d.item_code.nunique()} items  {d.district.nunique()} districts\n")

    if not frames:
        raise SystemExit("prices: no monthly files could be read")
    obs = pd.concat(frames, ignore_index=True)

    # Drop unit-entry errors (a kilo of rice keyed as a tonne) before any
    # median is taken. Per-item bounds, so a genuinely expensive item is safe.
    med = obs.groupby("item_code").price.transform("median")
    before = len(obs)
    obs = obs[(obs.price >= med * OUTLIER_LO) & (obs.price <= med * OUTLIER_HI)]
    sys.stderr.write(f"  trimmed {before - len(obs):,} outlier prices "
                     f"({(before - len(obs)) / before * 100:.2f}%)\n")
    return obs, keep_items, premises, present


def build_basket(obs, months):
    """The fixed basket: items priced in every month of the index window and
    stocked widely enough that a district-level median means something.

    `months` is the index window (the fully-published months to build the basket
    over). A sparse, still-being-collected trailing month is excluded by the
    caller BEFORE this is invoked - see `_index_months` in main()."""
    per_month = obs.groupby("item_code").ym.nunique()
    everywhere = set(per_month[per_month == len(months)].index)

    latest = obs[obs.ym == months[-1]]
    n_districts = latest.district.nunique()
    coverage = latest.groupby("item_code").district.nunique() / max(n_districts, 1)
    wide = set(coverage[coverage >= MIN_DISTRICT_COVERAGE].index)

    basket = sorted(everywhere & wide)
    sys.stderr.write(f"  basket: {len(basket)} items "
                     f"(in all {len(months)} months, >={MIN_DISTRICT_COVERAGE:.0%} districts)\n")
    return basket


def _index_months(obs, months):
    """Return the months the basket/index should be built over.

    A trailing month that is still being collected is sparse: it has a small
    fraction of the observations and items of a full month, so demanding every
    basket item appear in it collapses the basket (e.g. ~290 items -> ~47).
    When the last month is incomplete, drop it from the index window but keep
    it in `months` (the payload) so the UI can show it as the partial month.

    `months` is the ordered window passed by main(); returns (index_months,
    partial_ym) where index_months is the list to build the basket over and
    partial_ym is the trailing month to flag, or None if none is partial."""
    if len(months) < 2:
        return months, None

    last, prev = months[-1], months[-2]
    n_obs = {ym: len(g) for ym, g in obs.groupby("ym")}
    # A month that is still being collected carries a small share of a full
    # month's observations. Compare the last month to the month before it: if
    # the newest is clearly incomplete (< half the prior month's observations),
    # treat it as partial and build the index over the completed months.
    if n_obs.get(prev, 0) and n_obs.get(last, 0) < 0.5 * n_obs[prev]:
        return months[:-1], last
    return months, None


def jevons(medians, months, base_ym):
    """Jevons index (base month = 100) from a {ym: {item: median}} table.
    Uses only items priced in *every* month, so the basket cannot drift."""
    complete = [c for c in medians.columns
                if medians[c].notna().all()]
    if not complete or base_ym not in medians.index:
        return None, 0
    rel = medians[complete] / medians.loc[base_ym, complete]
    out = [r(geomean(rel.loc[ym]) * 100, 2) if ym in rel.index else None
           for ym in months]
    return out, len(complete)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--months", type=int, default=WINDOW_MONTHS)
    args = ap.parse_args()

    wanted = month_keys(args.months)
    obs, items, premises, months = load(wanted)
    # A trailing month still being collected is sparse; build the basket and
    # index over the completed months only, keeping the partial month in the
    # payload (flagged) so the UI can show it as work-in-progress.
    index_months, partial_ym = _index_months(obs, months)
    basket = build_basket(obs, index_months)
    if not basket:
        raise SystemExit("prices: empty basket, refusing to write")

    b = obs[obs.item_code.isin(basket)]
    # The spatial snapshot (district index / cheapest / itemGeo) reflects a
    # *complete* month. When the trailing month is partial, use the last full
    # index month so those sections don't collapse to near-empty.
    spatial_ym = index_months[-1]
    as_of = str(obs.date.max())[:10]
    # The index window may exclude the partial trailing month; `months` (the
    # payload array) is what the chart labels use, so the index series must be
    # reindexed onto `months` to stay positionally aligned (null for a partial).
    # reindex fills missing slots with NaN; map through r() to null them so
    # json.dump emits null (not a literal NaN, which is invalid JSON).
    idx = lambda s: [r(v, 2) for v in s.reindex(months)]

    # ── 1. national + per-state index over time (Jevons, fixed basket) ────
    nat_med = b.pivot_table(index="ym", columns="item_code",
                            values="price", aggfunc="median").reindex(index_months)
    national, n_nat = jevons(nat_med, index_months, index_months[0])
    national = idx(pd.Series(national, index=index_months))

    # Each state's index is built from the items priced there in every month,
    # which is not quite the same set everywhere. A state's own series is
    # internally consistent (that is what the chart shows), but the level is
    # only loosely comparable between states - so ship the item count and let
    # the UI say so rather than implying a precision that isn't there.
    states = {}
    for state, g in b.groupby("state"):
        piv = g.pivot_table(index="ym", columns="item_code",
                            values="price", aggfunc="median").reindex(index_months)
        series, n = jevons(piv, index_months, index_months[0])
        if series and n >= MIN_DISTRICT_ITEMS:
            series = idx(pd.Series(series, index=index_months))
            states[state] = {"idx": series, "n": n}

    # ── 2. per-item monthly medians + MoM / YoY ───────────────────────────
    meta = items.set_index("item_code")
    item_rows = []
    for code in basket:
        col = nat_med[code] if code in nat_med.columns else None
        if col is None:
            continue
        pts = [r(col.get(ym), 2) for ym in index_months]
        # Pad the item series onto `months` so the UI table lines up (null for
        # the partial month), then compute MoM/YoY from the last two real points.
        pts = idx(pd.Series(pts, index=index_months))
        real_pts = [p for p in pts if p is not None]
        cur = real_pts[-1] if real_pts else None
        prev = real_pts[-2] if len(real_pts) > 1 else None
        first = real_pts[0] if real_pts else None
        m = meta.loc[code]
        item_rows.append({
            "c": int(code),
            "n": str(m.get("item") or "").strip(),
            "u": str(m.get("unit") or "").strip(),
            "g": str(m.get("item_group") or "").strip(),
            "k": str(m.get("item_category") or "").strip(),
            "p": pts,
            "mom": r((cur / prev - 1) * 100, 2) if cur and prev else None,
            "yoy": r((cur / first - 1) * 100, 2) if cur and first else None,
        })
    # Biggest movers first is the useful default ordering for a UI list.
    item_rows.sort(key=lambda x: (x["yoy"] is None, -(x["yoy"] or 0)))

    # ── 3. spatial price level per district (100 = national average) ──────
    # Ratio to the national median *per item*, then geometric mean, so a
    # district is never penalised for stocking a different slice of the
    # basket. Latest FULL month only - this is a snapshot, not a trend.
    cur_month = b[b.ym == spatial_ym]
    nat_now = cur_month.groupby("item_code").price.median()
    # `n` (observation count) rides along for itemGeo below. The district index
    # itself deliberately does NOT filter on it - adding a floor here would
    # silently move every published district number.
    d_med = cur_month.groupby(["state", "district", "item_code"]).price.agg(
        ["median", "size"]).reset_index()
    d_med = d_med.rename(columns={"median": "price", "size": "n"})
    d_med["rel"] = d_med.price / d_med.item_code.map(nat_now)

    districts = {}
    for (state, district), g in d_med.groupby(["state", "district"]):
        if len(g) < MIN_DISTRICT_ITEMS:
            continue
        idx = geomean(g.rel)
        if idx is None:
            continue
        districts[district] = {
            "s": state,
            "idx": r(idx * 100, 1),
            "ni": int(len(g)),
            "np": int(cur_month[cur_month.district == district].premise_code.nunique()),
        }

    # ── 4. cheapest premises per district, on relative prices ─────────────
    pmeta = premises.set_index("premise_code")
    p_med = cur_month.groupby(["district", "premise_code", "item_code"]).price.median()
    p_med = p_med.reset_index()
    # Compare each premise against its OWN district's median, so the ranking
    # answers "cheapest near me" rather than re-stating the district index.
    dist_item_med = cur_month.groupby(["district", "item_code"]).price.median()
    p_med["rel"] = p_med.price / pd.MultiIndex.from_frame(
        p_med[["district", "item_code"]]).map(dist_item_med)

    cheapest = {}
    for district, g in p_med.groupby("district"):
        if district not in districts:
            continue
        ranked = []
        for premise_code, pg in g.groupby("premise_code"):
            if len(pg) < MIN_PREMISE_ITEMS:
                continue
            rel = geomean(pg.rel)
            if rel is None or premise_code not in pmeta.index:
                continue
            pm = pmeta.loc[premise_code]
            ranked.append({
                "p": str(pm.get("premise") or "").strip(),
                "t": str(pm.get("premise_type") or "").strip(),
                "d": r((rel - 1) * 100, 1),   # % vs the district median basket
                "ni": int(len(pg)),
            })
        ranked.sort(key=lambda x: x["d"])
        if ranked:
            cheapest[district] = ranked[:TOP_PREMISES]

    # ── 5. cheapest / dearest districts per item ──────────────────────────
    # Same relative-price trick as the district index, but held at item level
    # instead of collapsed: rel is this district's median for THIS item over
    # the national median for it, so 0.88 means 12% below the national price.
    #
    # Only the extremes are shipped. The full 198x166 matrix is ~400 KB of
    # mostly uninteresting middle; the tails are what answers "where is this
    # cheapest". Districts must clear MIN_ITEM_DISTRICT_OBS for the item and
    # already carry a spatial index, so a district that failed the basket
    # thresholds cannot reappear here.
    ranked_geo = d_med[(d_med.n >= MIN_ITEM_DISTRICT_OBS)
                       & (d_med.district.isin(districts))]
    item_geo = {}
    for code, g in ranked_geo.groupby("item_code"):
        if len(g) < TOP_ITEM_DISTRICTS * 2:
            continue          # too few districts to speak of a spread at all
        g = g.sort_values("rel")
        pick = lambda rows: [[str(x.district), r((x.rel - 1) * 100, 1)]
                             for x in rows.itertuples()]
        item_geo[str(int(code))] = {
            "lo": pick(g.head(TOP_ITEM_DISTRICTS)),
            "hi": pick(g.tail(TOP_ITEM_DISTRICTS).iloc[::-1]),
            "nd": int(len(g)),
        }
    sys.stderr.write(f"  itemGeo: {len(item_geo)} items ranked across districts "
                     f"(>={MIN_ITEM_DISTRICT_OBS} obs each)\n")

    payload = {
        "generated": dt.date.today().isoformat(),
        "asOf": as_of,
        "months": months,
        # A trailing month still being collected - flagged so the UI marks the
        # final point as work-in-progress. Derived from the sparse-month check.
        "partial": partial_ym,
        "method": {
            "time": "jevons_fixed_basket",
            "space": "geomean_relative_to_national_median",
            "note": "equal-weighted; no expenditure weights are published at "
                    "item level, so this is an elementary aggregate, not CPI",
        },
        "basket": {
            "n": len(basket),
            "nIndex": n_nat,
            "base": months[0],
            "national": national,
            "states": states,
        },
        "items": item_rows,
        "districts": districts,
        "cheapest": cheapest,
        "itemGeo": item_geo,
    }

    with open(OUT, "w") as f:
        json.dump(payload, f, separators=(",", ":"))
    sizes = {k: len(json.dumps(v, separators=(",", ":")))
             for k, v in payload.items() if k not in ("generated", "asOf")}
    total = len(open(OUT).read())
    sys.stderr.write(f"wrote {OUT} ({total:,} bytes): "
                     + ", ".join(f"{k}={v:,}" for k, v in sizes.items()) + "\n")


if __name__ == "__main__":
    main()
