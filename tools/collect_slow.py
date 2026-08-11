#!/usr/bin/env python3
"""Daily slow-data collector for the mygov dashboard.

Fetches every non-real-time dataset the app renders and writes
public/slow.json in the exact shapes the browser loaders build, so visitors
spend zero API budget on data that changes at most daily:

  fuel      : fuelprice (weekly), hh_income (yearly)
  finance   : exchangerates monthly avg, exchangerates_daily_1200 (business-daily),
              trnsc_daily_fpx (daily), payment_instruments (monthly), interestrates (monthly)
  mobility  : registrations_type_fuel (monthly), ridership_ktmb_daily (daily)
  economy   : cpi_core, cpi_headline, lfs_month, gdp_qtr_real, cpi_state
              (monthly/qtr), epf_dividend, fdi_flows (quarterly)
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


# ── public + school holidays ──────────────────────────────────────────
# Transit ridership is driven by the holiday calendar more than by anything
# else in this dataset: the Feb 2026 Komuter spike is Chinese New Year (17
# Feb) and the level shift after it is Ramadan starting two days later. A
# chart that shows the spike without naming it invites the reader to invent
# an explanation, so the dates ride along in slow.json and the chart labels
# them. School breaks are equally load-bearing: they are the travel peak
# seasons (mid-year and year-end holidays), so the chart shades them too.
#
# Source: the Malaysia Calendar API (mycal) - MIT-licensed, data from the
# official gazette (JPM BKPP), JAKIM, KPM and MPM, hosted on Cloudflare
# Workers. data.gov.my publishes no holiday dataset (almanak_astronomi is
# moon phases). mycal carries per-state coverage, the school calendar
# (KPM cuti perayaan, Kumpulan A/B) and exam schedules - the Google ICS
# used previously was federal-only and had no school data.
# Mirrored into slow.json at collect time so the dashboard never hot-links
# the third-party Worker from the browser.
MYCAL = "https://mycal-api.huijun00100101.workers.dev/v1"
NOT_HOLIDAYS = {"Valentine's Day", "Easter Sunday", "Christmas Eve",
                "New Year's Eve", "Mother's Day", "Father's Day"}
# The ones that visibly move intercity travel get emphasis in the UI.
MAJOR = ("Chinese New Year", "Hari Raya", "Deepavali", "Ramadan",
         "Wesak", "National Day", "Malaysia Day", "Christmas Day",
         "Labour Day", "Maulidur Rasul")
HOL_FROM = 2024   # mycal's holiday archive starts here


def mycal(path, params):
    qs = "&".join(f"{k}={urllib.parse.quote(str(v))}" for k, v in params.items())
    req = urllib.request.Request(f"{MYCAL}/{path}?{qs}",
                                 headers={"Accept": "application/json",
                                          "User-Agent": "mygov/1.0 (+https://mygov.faizalmzain.com)"})
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.loads(r.read().decode("utf-8"))


def parse_mycal_holidays(data):
    """Pure: filter + shape a mycal /holidays payload into slow.json rows.

    data : list of mycal holiday dicts ({"date", "name":{"en",..}, "states":[...]})
    Returns [[YYYY-MM-DD, name, major, [states]], ...] sorted by date."""
    out = []
    for h in data or []:
        name = str(h.get("name", {}).get("en", "")).strip()
        if not name or name in NOT_HOLIDAYS:
            continue
        date = str(h.get("date", ""))
        if not date or date < f"{HOL_FROM}-01-01":
            continue
        states = [str(s) for s in h.get("states", []) if s]
        if not states:
            continue
        out.append([date, name,
                    1 if any(k in name for k in MAJOR) else 0,
                    states])
    out.sort(key=lambda r: r[0])
    return out


def holidays():
    """[[YYYY-MM-DD, name, major, [states]], …] - state-aware holidays from
    the mycal API. Each entry carries the snake_case state list it applies to
    (federal entries list all states), so the app can filter to the
    visitor's location. `major` is the UI-emphasis flag (travel-moving)."""
    out = []
    for year in range(HOL_FROM, dt.date.today().year + 2):
        try:
            d = mycal("holidays", {"year": year})
        except Exception as e:
            sys.stderr.write(f"  holidays {year}: {e} - skipped\n")
            continue
        out.extend(parse_mycal_holidays((d or {}).get("data", [])))
    out.sort(key=lambda r: r[0])
    sys.stderr.write(f"  holidays: {len(out)} entries "
                     f"({sum(h[2] for h in out)} major) from {HOL_FROM}\n")
    return out


def school_holidays():
    """[{type, group, start, end, name, days}, …] - KPM school breaks
    (Kumpulan A = Kedah/Kelantan/Terengganu Fri-Sat weekend; B = the rest).
    School breaks ARE travel peak seasons, so the chart shades them."""
    out = []
    for year in range(dt.date.today().year - 1, dt.date.today().year + 2):
        try:
            d = mycal("school/holidays", {"year": year})
        except Exception as e:
            sys.stderr.write(f"  school {year}: {e} - skipped\n")
            continue
        for h in (d or {}).get("data", []):
            out.append({
                "type": str(h.get("type", "")),
                "group": str(h.get("group", "")),
                "start": str(h.get("startDate", "")),
                "end": str(h.get("endDate", "")),
                "name": str(h.get("name", {}).get("en", "")),
                "days": h.get("days", 0),
            })
    out.sort(key=lambda r: r["start"])
    sys.stderr.write(f"  school: {len(out)} breaks\n")
    return out


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
        pinst = fetch("catalogue", "data-catalogue/", {
            "id": "payment_instruments", "sort": "date"})
        ir = fetch("catalogue", "data-catalogue/", {"id": "interestrates", "sort": "-date"})

        # Currencies tracked by the dashboard (order = column order in the
        # compact rows; the API returns ~27, these are the ones shown).
        FX_KEYS = ["usd", "gbp", "eur", "sgd", "idr", "cny", "jpy", "thb", "aud"]

        def fxrows(rows):
            return [[r["date"]] + [num(r.get(k)) for k in FX_KEYS]
                    for r in (rows or []) if r.get("usd") is not None]

        avg = fxrows([r for r in (fx or []) if r.get("indicator") == "avg"])
        dly = fxrows(fxd)

        # PayNet's monthly payment instruments: eight instruments x ~86 months,
        # compacted to per-instrument columns (the same shape the mobility
        # section uses for fuel) so the payload stays flat.
        pmonths, p_idx, p_pairs = [], {}, []
        for r in pinst or []:
            if r["date"] not in p_idx:
                p_idx[r["date"]] = len(pmonths)
                pmonths.append(r["date"])
            p_pairs.append((r["instrument"], p_idx[r["date"]],
                            num(r.get("value")), num(r.get("volume"))))
        pval, pvol = {}, {}
        for inst, i, v, vol in p_pairs:
            pval.setdefault(inst, [None] * len(pmonths))[i] = v
            pvol.setdefault(inst, [None] * len(pmonths))[i] = vol
        pay = {"months": pmonths, "value": pval, "volume": pvol}

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
        fdi = fetch("opendosm", "opendosm/", {"id": "fdi_flows"})
        fdi_rows = sorted([[r["date"], num(r.get("inflow")), num(r.get("outflow")),
                            num(r.get("net"))] for r in (fdi or [])], key=lambda x: x[0])

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

        # ── public + school holidays (mycal API; self-contained failure) ─
        hol = holidays()
        sch = school_holidays()

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
            "pay": pay,
            "ir": [[r.get("bank"), r["date"], r.get("rate"), num(r.get("value"))] for r in (ir or [])],
        },
        "mobility": {
            "months": months, "byFuel": by_fuel, "total": total,
            "rid": dense(rid, "service", "ridership"),
        },
        "economy": {
            "cpi": cpi, "states": [{"name": k, "pts": v} for k, v in states.items()],
            "epf": epf,
            "fdi": fdi_rows,
            "lfs": [[r["date"], num(r.get("u_rate")), num(r.get("p_rate")), num(r.get("lf_employed"))] for r in (lfs or [])],
            "gdp": [[r["date"], num(r.get("value"))] for r in (gdp or [])
                    if r.get("series") == "abs" or r.get("series") is None],
        },
        "population": {"trend": trend, "latest": latest, "ethnicity": ethnicity},
        "holidays": hol,
        "school": sch,
    }
    with open(OUT, "w") as f:
        json.dump(payload, f, separators=(",", ":"))
    sizes = {k: len(json.dumps(v, separators=(",", ":"))) for k, v in payload.items() if k != "generated"}
    sys.stderr.write(f"wrote {OUT} ({len(open(OUT).read())} bytes): "
                     + ", ".join(f"{k}={v}" for k, v in sizes.items()) + "\n")


if __name__ == "__main__":
    main()
