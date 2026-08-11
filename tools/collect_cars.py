"""Car sales collector: JPJ granular registrations from storage.data.gov.my.

Downloads per-year registration_transactions CSV files (transportation/
cars_YYYY.csv) and aggregates them into a compact payload for the
dashboard: monthly totals by fuel, EV share, top makers, fuel mix and
state split.

Source: https://storage.data.gov.my/transportation/cars_YYYY.csv
- 489,340 rows for 2026 (Jan-Jul), one row per registered car
- Columns: date_reg, type, maker, model, colour, fuel, state
- `state` is mostly "Rakan Niaga" (dealer registrations) - the state of
  the buyer is only present for a minority of rows, so the state split
  is labelled as such and never presented as a full national map.

Output: public/cars.json - small (target < 25 KB), KV-friendly.
"""

import json
import sys
import urllib.request
from datetime import date

import pandas as pd

OUT = "public/cars.json"
UA = {"User-Agent": "mygov-mcp/1.0 (+https://malaysia-at-a-glance.com)"}
YEAR = date.today().year

# Kept compact: what the dashboard actually charts. "overall" is the total;
# the rest are the fuel mix columns.
FUEL_ORDER = ["petrol", "electric", "hybrid_petrol", "greendiesel", "diesel"]


def fetch(url):
    req = urllib.request.Request(url, headers=UA)
    return urllib.request.urlopen(req, timeout=180).read()


def aggregate(df):
    """Pure: rows -> compact dashboard payload. Testable without network."""
    df = df.copy()
    df["m"] = pd.to_datetime(df["date_reg"]).dt.to_period("M").astype(str)
    months = sorted(df["m"].unique())
    idx = {m: i for i, m in enumerate(months)}
    n = len(months)

    total = [0] * n
    by_fuel = {f: [0] * n for f in FUEL_ORDER}
    for (m, fuel), g in df.groupby(["m", "fuel"]):
        v = int(len(g))
        total[idx[m]] += v
        if fuel in by_fuel:
            by_fuel[fuel][idx[m]] = v

    ev_share = []
    for i in range(n):
        ev = by_fuel["electric"][i]
        ev_share.append(round(ev / total[i] * 100, 1) if total[i] else None)

    makers = df["maker"].value_counts().head(12)
    top = [{"name": str(k), "n": int(v)} for k, v in makers.items()]

    ev_df = df[df["fuel"] == "electric"]
    ev_makers = ev_df["maker"].value_counts().head(8)
    ev_top = [{"name": str(k), "n": int(v)} for k, v in ev_makers.items()]

    fuel_mix = {str(k): int(v) for k, v in df["fuel"].value_counts().items()}

    states = df["state"].value_counts().head(8)
    state_split = [{"name": str(k), "n": int(v)} for k, v in states.items()]

    return {
        "year": int(months[0][:4]),
        "asOf": df["date_reg"].max(),
        "months": months,
        "total": total,
        "byFuel": by_fuel,
        "evShare": ev_share,
        "topMakers": top,
        "evMakers": ev_top,
        "fuelMix": fuel_mix,
        "stateSplit": state_split,
        "rows": int(len(df)),
    }


def main():
    # Current year + previous year (YoY needs a baseline; 2025 file is 50 MB).
    payloads = {}
    for y in (YEAR, YEAR - 1):
        url = f"https://storage.data.gov.my/transportation/cars_{y}.csv"
        sys.stderr.write(f"fetching {url}\n")
        try:
            raw = fetch(url)
        except Exception as e:
            sys.stderr.write(f"  {y}: {e} - skipped\n")
            continue
        df = pd.read_csv(io_bytes(raw))
        payloads[y] = aggregate(df)
        sys.stderr.write(f"  {y}: {len(df):,} rows\n")

    if YEAR not in payloads:
        raise SystemExit("cars: current-year file unavailable, refusing to write")

    out = {
        "generated": date.today().isoformat(),
        "note": ("JPJ registrations via data.gov.my granular dataset. "
                 "State column is mostly dealer ('Rakan Niaga') registrations, "
                 "so state split covers buyer-state rows only."),
        "series": payloads,
    }
    with open(OUT, "w") as f:
        json.dump(out, f, separators=(",", ":"))
    size = len(open(OUT).read())
    sys.stderr.write(f"wrote {OUT} ({size:,} bytes)\n")
    if size > 40_000:
        sys.stderr.write("warning: payload larger than expected\n")


def io_bytes(raw):
    import io
    return io.BytesIO(raw)


if __name__ == "__main__":
    main()
