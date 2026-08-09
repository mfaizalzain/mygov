#!/usr/bin/env python3
"""Daily slow-data collector for the mygov dashboard.

Fetches every non-real-time dataset the app renders and writes
public/slow.json in the exact shapes the browser loaders build, so visitors
spend zero API budget on data that changes at most daily:

  fuel      : fuelprice (weekly), hh_income (yearly)
  finance   : exchangerates monthly avg, exchangerates_daily_1200 (business-daily),
              trnsc_daily_fpx (daily), interestrates (monthly)
  mobility  : registrations_type_fuel (monthly), ridership_ktmb_daily (daily)
  economy   : cpi_core, cpi_headline, lfs_month, gdp_qtr_real, cpi_state
              (monthly/qtr), epf_dividend
  population: population_malaysia (annual)

Run:  python3 tools/collect_slow.py
Writes: public/slow.json  (committed by the GitHub Action, auto-deployed)

The app reads slow.json same-origin and only falls back to the live API when
it is missing or older than STALE_DAYS. The Action runs twice a day so the
daily series stay within ~12h of current.
"""
import datetime as dt
import json
import sys
import time
import urllib.parse
import urllib.request

BASE = "https://api.data.gov.my/"
OUT = "public/slow.json"
STALE_DAYS = 5


def fetch(family, path, params):
    qs = "&".join(f"{k}={urllib.parse.quote(str(v))}" for k, v in params.items())
    url = BASE + path + "?" + qs
    last = None
    for attempt in range(4):
        try:
            req = urllib.request.Request(url, headers={"Accept": "application/json"})
            with urllib.request.urlopen(req, timeout=90) as r:
                return json.loads(r.read().decode("utf-8"))
        except Exception as e:
            last = e
            sys.stderr.write(f"  attempt {attempt + 1}/4 failed for {url[:80]}: {e}\n")
            if attempt < 3:
                time.sleep(5 * (attempt + 1))   # 5s, 10s, 15s backoff
    if last is not None:
        raise last
    raise RuntimeError(f"fetch failed for {url}")


def num(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def dense(rows, key_col, val_col):
    """Mirror of the app's denseDaily(): start day + flat arrays (~5x smaller)."""
    acc = {}
    lo, hi = float("inf"), float("-inf")
    for r in rows or []:
        day = int(round(dt.date.fromisoformat(r["date"]).toordinal() - dt.date(1970, 1, 1).toordinal()))
        lo, hi = min(lo, day), max(hi, day)
        k = str(r[key_col]) if key_col else "value"
        v = num(r.get(val_col))
        if v is None:
            continue
        acc.setdefault(k, {})[day] = v
    if not acc:
        return {"t0": 0, "n": 0, "keys": [], "series": {}}
    n = int(hi - lo + 1)
    series = {}
    for k, m in acc.items():
        a = [None] * n
        for day, v in m.items():
            a[int(day - lo)] = v
        series[k] = a
    return {"t0": int(lo), "n": n, "keys": list(acc.keys()), "series": series}


def days_back(n):
    return (dt.date.today() - dt.timedelta(days=n)).isoformat()


def main():
    today = dt.date.today().isoformat()
    try:
        # ── fuel (data-catalogue) ──────────────────────────────────────
        fuel = fetch("catalogue", "data-catalogue/", {"id": "fuelprice", "filter": "level@series_type"})
        hh = fetch("catalogue", "data-catalogue/", {"id": "hh_income"})
        lv = sorted(fuel or [], key=lambda r: r["date"])
        hh_rows = [[r["date"], num(r.get("income_mean")), num(r.get("income_median"))] for r in (hh or [])]
        hh_latest = hh_rows[-1][0][:10] if hh_rows else None

        # ── finance (data-catalogue) ───────────────────────────────────
        fx = fetch("catalogue", "data-catalogue/", {"id": "exchangerates", "sort": "-date"})
        fxd = fetch("catalogue", "data-catalogue/", {
            "id": "exchangerates_daily_1200", "filter": "middle@rate_type",
            "date_start": days_back(3 * 365) + "@date", "sort": "date"})
        fpx = fetch("catalogue", "data-catalogue/", {
            "id": "trnsc_daily_fpx", "filter": "both@model", "sort": "date"})
        ir = fetch("catalogue", "data-catalogue/", {"id": "interestrates", "sort": "-date"})

        def fxrows(rows):
            return [[r["date"], num(r.get("usd")), num(r.get("gbp")), num(r.get("eur")),
                     num(r.get("sgd")), num(r.get("idr"))]
                    for r in (rows or []) if r.get("usd") is not None]

        avg = fxrows([r for r in (fx or []) if r.get("indicator") == "avg"])
        dly = fxrows(fxd)

        # ── mobility (data-catalogue) ──────────────────────────────────
        reg = fetch("catalogue", "data-catalogue/", {
            "id": "registrations_type_fuel", "filter": "all_types@type", "sort": "date"})
        rid = fetch("catalogue", "data-catalogue/", {"id": "ridership_ktmb_daily", "sort": "date"})
        months, m_idx, pairs, total = [], {}, [], []
        for r in reg or []:
            if r["date"] not in m_idx:
                m_idx[r["date"]] = len(months)
                months.append(r["date"])
            i = m_idx[r["date"]]
            if r.get("fuel") == "all_fuels":
                total.append(num(r.get("registrations")))
            else:
                pairs.append((r["fuel"], i, num(r.get("registrations"))))
        by_fuel = {f: [None] * len(months) for f in ("electric", "hybrid", "greendiesel", "petrol", "diesel", "other")}
        for fuel_name, i, v in pairs:
            if fuel_name in by_fuel and v is not None:
                by_fuel[fuel_name][i] = v

        # ── economy (opendosm + one catalogue epf call) ────────────────
        core = fetch("opendosm", "opendosm/", {"id": "cpi_core"})
        head = fetch("opendosm", "opendosm/", {"id": "cpi_headline", "filter": "overall@division"})
        lfs = fetch("opendosm", "opendosm/", {"id": "lfs_month"})
        gdp = fetch("opendosm", "opendosm/", {"id": "gdp_qtr_real"})
        st = fetch("opendosm", "opendosm/", {
            "id": "cpi_state", "filter": "overall@division",
            "date_start": days_back(3 * 365) + "@date"})
        epf_rows = fetch("catalogue", "data-catalogue/", {
            "id": "epf_dividend", "sort": "-date", "limit": 1})
        epf = None
        if epf_rows:
            epf = {"date": epf_rows[0]["date"], "shariah": epf_rows[0].get("shariah"),
                   "conventional": epf_rows[0].get("conventional")}

        def by_div(rows):
            m = {}
            for r in rows or []:
                d = r.get("division") or "overall"
                m.setdefault(d, []).append([r["date"], num(r.get("index"))])
            for v in m.values():
                v.sort(key=lambda x: x[0])
            return [{"name": k, "pts": v} for k, v in m.items()]

        cpi = by_div(core)
        hp = sorted([[r["date"], num(r.get("index"))] for r in (head or [])], key=lambda x: x[0])
        if hp:
            cpi.insert(0, {"name": "headline", "pts": hp})
        states = {}
        for r in st or []:
            if not r.get("state"):
                continue
            states.setdefault(r["state"], []).append([r["date"], num(r.get("index"))])
        for v in states.values():
            v.sort(key=lambda x: x[0])

        # ── population (opendosm) ──────────────────────────────────────
        pop = fetch("opendosm", "opendosm/", {
            "id": "population_malaysia", "filter": "overall@age", "sort": "date"})
        both = [r for r in (pop or []) if r.get("sex") == "both"]
        trend = sorted([[r["date"], num(r.get("population"))] for r in both
                        if r.get("ethnicity") == "overall"], key=lambda x: x[0])
        latest = trend[-1][0] if trend else None
        ethnicity = [[r["ethnicity"], num(r.get("population"))] for r in both
                     if r.get("date") == latest and r.get("ethnicity") != "overall"]

    except Exception as e:
        sys.stderr.write(f"fetch failed: {e}\n")
        raise SystemExit(1)

    payload = {
        "generated": today,
        "fuel": {
            "rows": [[r["date"], num(r.get("ron95")), num(r.get("ron97")), num(r.get("diesel"))] for r in lv],
            "latest": (lv[-1] if lv else None),
            "prev": (lv[-2] if len(lv) > 1 else None),
            "hh": hh_rows, "hhFresh": bool(hh_latest), "hhLatest": hh_latest,
        },
        "finance": {
            "fx": avg, "fxd": dly,
            "fpx": [[r["date"], num(r.get("value")), num(r.get("volume"))] for r in (fpx or [])],
            "ir": [[r.get("bank"), r["date"], r.get("rate"), num(r.get("value"))] for r in (ir or [])],
        },
        "mobility": {
            "months": months, "byFuel": by_fuel, "total": total,
            "rid": dense(rid, "service", "ridership"),
        },
        "economy": {
            "cpi": cpi, "states": [{"name": k, "pts": v} for k, v in states.items()],
            "epf": epf,
            "lfs": [[r["date"], num(r.get("u_rate")), num(r.get("p_rate")), num(r.get("lf_employed"))] for r in (lfs or [])],
            "gdp": [[r["date"], num(r.get("value"))] for r in (gdp or [])
                    if r.get("series") == "abs" or r.get("series") is None],
        },
        "population": {"trend": trend, "latest": latest, "ethnicity": ethnicity},
    }
    with open(OUT, "w") as f:
        json.dump(payload, f, separators=(",", ":"))
    sizes = {k: len(json.dumps(v, separators=(",", ":"))) for k, v in payload.items() if k != "generated"}
    sys.stderr.write(f"wrote {OUT} ({len(open(OUT).read())} bytes): "
                     + ", ".join(f"{k}={v}" for k, v in sizes.items()) + "\n")


if __name__ == "__main__":
    main()
