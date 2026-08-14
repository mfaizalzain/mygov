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
OUT = os.environ.get("ALERTS_OUT", "public/alerts.json")
EQ_RADIUS_KM = 500
EQ_FRESH_MS = 12 * 3600 * 1000


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
