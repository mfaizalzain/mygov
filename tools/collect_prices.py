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
    """The fixed basket: items priced in every month of the window and stocked
    widely enough that a district-level median means something."""
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
    basket = build_basket(obs, months)
    if not basket:
        raise SystemExit("prices: empty basket, refusing to write")

    b = obs[obs.item_code.isin(basket)]
    latest_ym = months[-1]
    as_of = str(obs.date.max())[:10]

    # ── 1. national + per-state index over time (Jevons, fixed basket) ────
    nat_med = b.pivot_table(index="ym", columns="item_code",
                            values="price", aggfunc="median").reindex(months)
    national, n_nat = jevons(nat_med, months, months[0])

    # Each state's index is built from the items priced there in every month,
    # which is not quite the same set everywhere. A state's own series is
    # internally consistent (that is what the chart shows), but the level is
    # only loosely comparable between states - so ship the item count and let
    # the UI say so rather than implying a precision that isn't there.
    states = {}
    for state, g in b.groupby("state"):
        piv = g.pivot_table(index="ym", columns="item_code",
                            values="price", aggfunc="median").reindex(months)
        series, n = jevons(piv, months, months[0])
        if series and n >= MIN_DISTRICT_ITEMS:
            states[state] = {"idx": series, "n": n}

    # ── 2. per-item monthly medians + MoM / YoY ───────────────────────────
    meta = items.set_index("item_code")
    item_rows = []
    for code in basket:
        col = nat_med[code] if code in nat_med.columns else None
        if col is None:
            continue
        pts = [r(col.get(ym), 2) for ym in months]
        cur, prev = pts[-1], (pts[-2] if len(pts) > 1 else None)
        first = pts[0]
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
    # basket. Latest month only - this is a snapshot, not a trend.
    cur_month = b[b.ym == latest_ym]
    nat_now = cur_month.groupby("item_code").price.median()
    d_med = cur_month.groupby(["state", "district", "item_code"]).price.median()
    d_med = d_med.reset_index()
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

    payload = {
        "generated": dt.date.today().isoformat(),
        "asOf": as_of,
        "months": months,
        # The newest month is still being collected; the UI should mark it.
        "partial": latest_ym if latest_ym == month_keys(1)[0] else None,
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
