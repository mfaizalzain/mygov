#!/usr/bin/env python3
"""Daily transport-activity snapshot for the mygov dashboard.

KTM has a published daily-ridership history, but the modes that actually
move Malaysia - air travel and buses - have NO public historical series:
the FIDS feed is live-only and Prasarana publishes no ridership. The only
way to build an honest air+bus trend is to accumulate it ourselves: once a
day, snapshot how much transport is scheduled/flown, append to a history
held in Cloudflare KV, and let the dashboard plot it after a few months.

Two numbers per day (chosen to be deterministic and reproducible):

  kul_flights : scheduled flight movements at KLIA + KLIA2 for TODAY,
                from the Malaysia Airports FIDS API (arrivals + departures).
  bus_trips   : scheduled Rapid KL bus trips for TODAY, from the data.gov.my
                GTFS-static feed (frequencies.txt × trips.txt). Fully
                deterministic - the schedule does not change day to day, so
                any day's value can be recomputed from the same feed.

The snapshot also captures a 7-day rolling history so a chart can show
weekday seasonality immediately, without waiting for the series to grow.

Run:  python3 tools/collect_transport.py
Writes: public/transport_history.json  (pushed to KV key 'transport' by the
Action; static file is the cold-start fallback)

Env:
  FIDS_API_KEY  (Malaysia Airports API key; also a GitHub secret)
"""
import datetime as dt
import io
import json
import os
import sys
import urllib.parse
import urllib.request
import zipfile

OUT = "public/transport_history.json"

GTFS = "https://api.data.gov.my/gtfs-static/prasarana?category=rapid-bus-kl"
FIDS = "https://api.myairports.com.my/passenger-fids/api/flights/search-flights"


def ua():
    return {"User-Agent": "mygov/1.0 (+https://malaysia-at-a-glance.com)"}


def fetch(url, headers=None):
    h = ua()
    if headers:
        h.update(headers)
    req = urllib.request.Request(url, headers=h)
    with urllib.request.urlopen(req, timeout=90) as r:
        return r.read()


def count_trips_for_day(cal, dates, trip_services, day):
    """Pure core of scheduled_bus_trips - no I/O, fully deterministic.

    cal      : {service_id: {"days": [7x0/1], "start": YYYY-MM-DD, "end": ...}}
    dates    : {service_id: {YYYY-MM-DD: True/False}} exceptions (calendar_dates)
    trip_services : [service_id, ...] one per trip (trips.txt)
    day      : ISO date to count for
    Returns the number of trips whose service runs that day."""
    wd = dt.date.fromisoformat(day)
    weekday_idx = wd.weekday()  # 0=Mon..6=Sun

    def active(sid):
        if sid in dates and day in dates[sid]:
            return dates[sid][day]
        c = cal.get(sid)
        if not c:
            return False
        if not (c["start"] <= day <= c["end"]):
            return False
        return c["days"][weekday_idx] == "1"

    return sum(1 for sid in trip_services if active(sid))


def parse_gtfs(zf):
    """Extract (cal, dates, trip_services) from an open GTFS zipfile."""
    cal = {}
    for line in zf.read("calendar.txt").decode().splitlines()[1:]:
        p = line.split(",")
        if len(p) >= 10:
            # columns: service_id, mon..sun (7), start_date, end_date
            cal[p[0]] = {"days": p[1:8], "start": p[8], "end": p[9]}
    dates = {}  # service_id -> 1 added / 0 removed
    if "calendar_dates.txt" in zf.namelist():
        for line in zf.read("calendar_dates.txt").decode().splitlines()[1:]:
            p = line.split(",")
            if len(p) >= 3:
                dates.setdefault(p[0], {})[p[1]] = p[2] == "1"
    trip_services = []
    for line in zf.read("trips.txt").decode().splitlines()[1:]:
        p = line.split(",")
        if len(p) >= 3:
            trip_services.append(p[1])
    return cal, dates, trip_services


def scheduled_bus_trips(day):
    """Count Rapid KL bus trips scheduled to run on `day` (ISO date).

    GTFS frequencies.txt gives per-trip headways; a trip with a frequency
    entry runs for its whole service span, so 'trip runs today' is
    determined by the calendar (weekday vs weekend service) plus any
    calendar_dates exception. Deterministic: same feed, same answer."""
    raw = fetch(GTFS)
    zf = zipfile.ZipFile(io.BytesIO(raw))
    cal, dates, trip_services = parse_gtfs(zf)
    return count_trips_for_day(cal, dates, trip_services, day)


def kul_flights_today(api_key):
    """Total scheduled movements (arrivals + departures) at KLIA & KLIA2."""
    total = 0
    for terminal in ("KLIA", "KLIA2"):
        for code in ("A", "D"):
            qs = urllib.parse.urlencode({
                "code": code, "key": "all", "terminal": terminal,
                "dayKey": "0", "live": "true", "skip": "0", "take": "200"})
            try:
                raw = fetch(f"{FIDS}?{qs}",
                            {"x-api-key": api_key, "accept": "application/json"})
                data = json.loads(raw)
                total += len((data.get("flightStatuses") or []) if isinstance(data, dict) else (data or []))
            except Exception as e:
                sys.stderr.write(f"  fids {terminal} {code}: {e}\n")
    return total


def main():
    today = dt.date.today().isoformat()
    try:
        with open(OUT) as f:
            hist = json.load(f)
    except (OSError, ValueError):
        hist = {"days": [], "source": "FIDS + data.gov.my GTFS-static (rapid-bus-kl)"}

    days = {d["date"]: d for d in hist["days"]}
    if today in days:
        # Idempotency guard. Backfill a flight count that a previous run
        # could not record (FIDS down at cron time, or a seed row) rather
        # than leaving an honest-looking null forever.
        row = days[today]
        api_key = os.environ.get("FIDS_API_KEY", "")
        if row.get("kul_flights") is None and api_key:
            try:
                row["kul_flights"] = kul_flights_today(api_key)
                sys.stderr.write(f"  {today}: backfilled kul_flights={row['kul_flights']}\n")
            except Exception as e:
                sys.stderr.write(f"  fids backfill failed: {e}\n")
            ordered = sorted(days.values(), key=lambda d: d["date"])[-120:]
            hist["days"] = ordered
            hist["updated"] = today
            with open(OUT, "w") as f:
                json.dump(hist, f, separators=(",", ":"))
        else:
            sys.stderr.write(f"  {today} already snapshotted - nothing to do\n")
        return

    bus = scheduled_bus_trips(today)
    flights = 0
    api_key = os.environ.get("FIDS_API_KEY", "")
    if api_key:
        flights = kul_flights_today(api_key)
    else:
        sys.stderr.write("  FIDS_API_KEY unset - flights=0\n")

    days[today] = {
        "date": today,
        "bus_trips": bus,
        "kul_flights": flights,
        "weekday": dt.date.fromisoformat(today).strftime("%a"),
    }
    # Keep a rolling 120-day window (4 months) - plenty for a trend line.
    ordered = sorted(days.values(), key=lambda d: d["date"])[-120:]
    hist["days"] = ordered
    hist["updated"] = today

    with open(OUT, "w") as f:
        json.dump(hist, f, separators=(",", ":"))
    sys.stderr.write(f"wrote {OUT}: {len(ordered)} days "
                     f"(bus_trips={bus}, kul_flights={flights})\n")


if __name__ == "__main__":
    main()
