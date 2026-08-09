#!/usr/bin/env python3
"""Daily KKM (Ministry of Health) health data collector.

Fetches the three MoH daily series from the data.gov.my catalogue and writes
them to public/health.json in the same compact shape the dashboard's
loadHealth() builds in the browser ({t0, n, keys, series} per series), so the
app can read a same-origin static file instead of spending 3 of its 4-per-minute
data-catalogue requests on every visitor load.

Run:  python3 tools/collect_health.py
Writes: public/health.json  (committed by the GitHub Action, auto-deployed)
"""
import json
import sys
import time
import urllib.parse
import urllib.request

BASE = "https://api.data.gov.my/data-catalogue/"
OUT = "public/health.json"
DAY_MS = 86400000.0
YEAR_MS = 365.25 * DAY_MS


def fetch(params):
    qs = "&".join(f"{k}={urllib.parse.quote(str(v))}" for k, v in params.items())
    url = BASE + "?" + qs
    last = None
    for attempt in range(4):
        try:
            req = urllib.request.Request(url, headers={"Accept": "application/json"})
            with urllib.request.urlopen(req, timeout=60) as r:
                return json.loads(r.read().decode("utf-8"))
        except Exception as e:
            last = e
            sys.stderr.write(f"  attempt {attempt + 1}/4 failed for {url[:80]}: {e}\n")
            if attempt < 3:
                time.sleep(5 * (attempt + 1))   # 5s, 10s, 15s backoff
    if last is not None:
        raise last
    raise RuntimeError(f"fetch failed for {url}")


def dense(rows, key_col, val_col):
    """Same as the app's denseDaily(): start day + flat arrays, ~5x smaller."""
    acc = {}
    lo, hi = float("inf"), float("-inf")
    for r in rows or []:
        day = int(round(__import__("datetime").datetime.fromisoformat(r["date"]).timestamp() * 1000 / DAY_MS))
        lo, hi = min(lo, day), max(hi, day)
        k = str(r[key_col]) if key_col else "value"
        v = r.get(val_col)
        try:
            v = float(v)
        except (TypeError, ValueError):
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


def main():
    import datetime as dt
    # 3-year window for donations (the app's range toggle never reaches further)
    cutoff = (dt.date.today() - dt.timedelta(days=3 * 365)).isoformat()
    try:
        don = fetch({"id": "blood_donations", "date_start": cutoff + "@date", "sort": "date"})
        organ = fetch({"id": "organ_pledges", "sort": "date"})
        peka = fetch({"id": "pekab40_screenings", "sort": "date"})
    except Exception as e:
        sys.stderr.write(f"fetch failed: {e}\n")
        raise SystemExit(1)

    D = dense(don, "blood_type", "donations")
    O = dense(organ, None, "pledges")
    P = dense(peka, None, "screenings")

    # newest date across the three series
    latest = max(
        (s["t0"] + s["n"] - 1 for s in (D, O, P) if s["n"]),
        default=0,
    )
    updated = dt.date.fromtimestamp(latest * DAY_MS / 1000).isoformat()

    payload = {"updated": updated, "don": D, "organ": O, "peka": P}
    with open(OUT, "w") as f:
        json.dump(payload, f, separators=(",", ":"))
    sys.stderr.write(f"wrote {OUT}: updated={updated} "
                     f"don={D['n']}d organ={O['n']}d peka={P['n']}d\n")


if __name__ == "__main__":
    main()
