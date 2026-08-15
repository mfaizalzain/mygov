#!/usr/bin/env python3
"""Collect the combined hazard summary served by /api/alerts.

The Worker route combines earthquakes within 500 km of Malaysia and current
JPS flood risk. Both upstream feeds are large enough that this aggregation
should happen on a schedule, not per visitor.

Run:   python3 tools/collect_alerts.py
Writes: public/alerts.json
Pushes: KV key "alerts" (via kv_upload.py push alerts)
"""

import json
import math
import os
import re
import sys
import time
import urllib.request
from datetime import datetime, timezone

from collect_flood import (
    FEED as FLOOD_FEED,
    FRESH_MS as FLOOD_FRESH_MS,
    RECEDING,
    UA,
    WATCH,
    num,
    parse_ts,
)

EARTHQUAKE_FEED = "https://api.data.gov.my/weather/warning/earthquake"
# Second source, because the first one stopped being live. Checked 15 Aug 2026
# with the cache bypassed: MET's feed's newest event was six days old and it did
# not contain that morning's M6.9 at Pematangsiantar, 268 km from the Perak
# coast. Over the preceding 30 days MET listed 2 events within 500 km; USGS
# listed 8. Both are merged - MET is the Malaysian authority and carries local
# bearing text - but USGS is what makes the feed live.
USGS_FEED = "https://earthquake.usgs.gov/earthquakes/feed/v1.0/summary/2.5_week.geojson"
OUT = os.environ.get("ALERTS_OUT", "public/alerts.json")
EQ_RADIUS_KM = 500
# Coast and border anchors, one per stretch of Malaysia that could be nearest
# land to a regional quake. Keep in step with MY_ANCHORS in public/app.js.
MY_ANCHORS = [
    ("Langkawi, Kedah", 6.35, 99.80),
    ("George Town, Pulau Pinang", 5.41, 100.33),
    ("Bagan Datuk, Perak", 4.60, 100.90),
    ("Klang, Selangor", 3.10, 101.60),
    ("Kota Bharu, Kelantan", 6.13, 102.24),
    ("Kuantan, Pahang", 3.80, 103.33),
    ("Johor Bahru, Johor", 1.50, 103.70),
    ("Kuching, Sarawak", 1.55, 110.35),
    ("Bintulu, Sarawak", 3.17, 113.03),
    ("Miri, Sarawak", 4.40, 114.00),
    ("Kota Kinabalu, Sabah", 5.98, 116.07),
    ("Kudat, Sabah", 6.90, 116.80),
    ("Semporna, Sabah", 4.48, 118.60),
]
# One week, matching app.js EQ_FRESH_MS. Quakes within 500 km of Malaysia occur
# about 1.5 times a month, so the previous 12-hour window meant the alert had
# something to show roughly 0.3% of the year. The frontend keeps its own
# 24-hour cut for what counts as an *active* alert in the nav badge.
EQ_FRESH_MS = 7 * 24 * 3600 * 1000


def haversine(lat1, lon1, lat2, lon2):
    r = 6371.0
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = (math.sin(dlat / 2) ** 2
         + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2))
         * math.sin(dlon / 2) ** 2)
    return 2 * r * math.asin(math.sqrt(a))


def km_from_malaysia(lat, lon):
    """Distance to the nearest Malaysian anchor: (km, "Place, State").

    This is the same question MET's own n_distancemas field answers, so the two
    sources' cards read alike.
    """
    best, who = float("inf"), None
    for name, alat, alon in MY_ANCHORS:
        d = haversine(lat, lon, alat, alon)
        if d < best:
            best, who = d, name
    return best, who


def parse_quake_ts(raw):
    s = str(raw or "").replace(" ", "T")
    if not s:
        return None
    try:
        s = s if s.endswith("Z") else s + "Z"
        return int(datetime.fromisoformat(s).astimezone(timezone.utc).timestamp() * 1000)
    except ValueError:
        return None


def main():
    now = int(time.time() * 1000)

    quakes = []
    try:
        req = urllib.request.Request(EARTHQUAKE_FEED, headers={"User-Agent": UA})
        with urllib.request.urlopen(req, timeout=45) as r:
            rows = json.loads(r.read().decode("utf-8", "replace"))
    except Exception as e:
        sys.stderr.write(f"alerts: earthquake fetch failed: {e}\n")
        rows = []

    for q in rows if isinstance(rows, list) else []:
        dist = str(q.get("n_distancemas") or "")
        m = re.search(r"([\d,]+)\s*km", dist, re.I)
        if not m:
            continue
        km = float(m.group(1).replace(",", ""))
        if km > EQ_RADIUS_KM:
            continue
        ts = parse_quake_ts(q.get("utcdatetime"))
        if not ts or now - ts > EQ_FRESH_MS:
            continue
        quakes.append({
            "mag": num(q.get("magdefault")),
            "type": str(q.get("magtypedefault") or ""),
            "place": str(q.get("location_original") or q.get("location") or ""),
            "lat": num(q.get("lat")),
            "lon": num(q.get("lon")),
            "depth": num(q.get("depth")),
            "km": km,
            "dist": dist,
            "ts": ts,
        })
    for q in quakes:
        q["src"] = "MET"

    # USGS, same radius and window, distance computed here because their feed
    # has no notion of Malaysia. A failure here leaves MET's rows standing.
    usgs = []
    try:
        req = urllib.request.Request(USGS_FEED, headers={"User-Agent": UA})
        with urllib.request.urlopen(req, timeout=45) as r:
            feats = json.loads(r.read().decode("utf-8", "replace")).get("features", [])
    except Exception as e:
        sys.stderr.write(f"alerts: usgs fetch failed: {e}\n")
        feats = []

    for f in feats:
        c = (f.get("geometry") or {}).get("coordinates") or []
        p = f.get("properties") or {}
        if len(c) < 2 or not isinstance(p.get("time"), (int, float)):
            continue
        lon, lat = num(c[0]), num(c[1])
        if lat is None or lon is None:
            continue
        km, who = km_from_malaysia(lat, lon)
        ts = int(p["time"])
        if km > EQ_RADIUS_KM or now - ts > EQ_FRESH_MS:
            continue
        usgs.append({
            "mag": num(p.get("mag")),
            "type": str(p.get("magType") or ""),
            "place": str(p.get("place") or ""),
            "lat": lat, "lon": lon,
            "depth": num(c[2]) if len(c) > 2 else None,
            "km": round(km, 1),
            "dist": f"{round(km)}km from {who}",
            "ts": ts,
            "src": "USGS",
        })

    # Merge: the same rupture differs slightly between agencies, so "same
    # event" is a tolerance - two minutes and 150 km. MET's row wins.
    for u in usgs:
        if not any(abs(m["ts"] - u["ts"]) < 120_000
                   and haversine(m["lat"], m["lon"], u["lat"], u["lon"]) < 150
                   for m in quakes if m.get("lat") is not None):
            quakes.append(u)

    quakes.sort(key=lambda q: q["ts"], reverse=True)

    flood = {"at_risk": 0, "danger": 0, "warning": 0, "alert": 0, "top": []}
    try:
        req = urllib.request.Request(FLOOD_FEED, headers={"User-Agent": UA})
        with urllib.request.urlopen(req, timeout=60) as r:
            rows = json.loads(r.read().decode("utf-8", "replace"))
    except Exception as e:
        sys.stderr.write(f"alerts: flood fetch failed: {e}\n")
        rows = []

    for s in rows if isinstance(rows, list) else []:
        status = str(s.get("n") or "")
        if status not in WATCH:
            continue
        trend = str(s.get("s") or "")
        if status != "Danger" and trend in RECEDING:
            continue
        ts = parse_ts(s.get("q"))
        if not ts or now - ts > FLOOD_FRESH_MS:
            continue
        flood["at_risk"] += 1
        if status == "Danger":
            flood["danger"] += 1
        elif status == "Warning":
            flood["warning"] += 1
        else:
            flood["alert"] += 1
        if len(flood["top"]) < 5:
            flood["top"].append({
                "name": str(s.get("b") or ""),
                "state": str(s.get("f") or ""),
                "level": num(s.get("m")),
                "dangerLevel": num(s.get("o")),
                "status": status,
                "trend": trend,
                "ts": ts,
            })

    out = {
        "updated": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "earthquakes": quakes,
        "flood": flood,
    }
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=1)
    print(f"alerts: wrote {len(quakes)} quakes and {flood['at_risk']} "
          f"flood stations -> {OUT}")


if __name__ == "__main__":
    main()
