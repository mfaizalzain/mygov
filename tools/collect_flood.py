#!/usr/bin/env python3
"""Collect JPS flood-gauge telemetry into the slim /api/flood payload.

The upstream feed is ~1.3 MB of all 2700+ stations. The Worker previously
downloaded and filtered it on every /api/flood request; this collector does
that once per run and stores the at-risk stations under KV key "flood".

Run:   python3 tools/collect_flood.py
Writes: public/flood.json
Pushes: KV key "flood" (via kv_upload.py push flood)
"""

import json
import math
import os
import re
import sys
import time
import urllib.request
from datetime import datetime, timedelta, timezone

UA = "mygov-dashboard/1.0 (+https://mygov.faizalmzain.com)"
FEED = "https://publicinfobanjir.water.gov.my/wp-content/themes/enlighten/data/latestreadingstrendabc.json"
OUT = os.environ.get("FLOOD_OUT", "public/flood.json")

MYT = timezone(timedelta(hours=8))
WATCH = {"Danger", "Warning", "Alert"}
RECEDING = {"Receding", "Falling"}
FRESH_MS = 24 * 3600 * 1000


def parse_ts(raw):
    s = str(raw or "")
    m = re.match(r"^(\d{2})/(\d{2})/(\d{4})[ T](\d{2}):(\d{2})", s)
    if not m:
        return None
    day, month, year, hour, minute = (int(m.group(i)) for i in range(1, 6))
    try:
        dt = datetime(year, month, day, hour, minute, tzinfo=MYT)
        return int(dt.timestamp() * 1000)
    except ValueError:
        return None


def num(v):
    if v is None:
        return None
    try:
        n = float(v)
    except (TypeError, ValueError):
        return None
    return n if math.isfinite(n) else None


def main():
    try:
        req = urllib.request.Request(FEED, headers={"User-Agent": UA})
        with urllib.request.urlopen(req, timeout=60) as r:
            rows = json.loads(r.read().decode("utf-8", "replace"))
    except Exception as e:
        sys.exit(f"flood: upstream fetch failed: {e}")

    now = int(time.time() * 1000)
    updated = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    stations = []
    state_stats = {}
    for s in rows if isinstance(rows, list) else []:
        status = str(s.get("n") or "")
        if status not in WATCH:
            continue
        trend = str(s.get("s") or "")
        if status != "Danger" and trend in RECEDING:
            continue
        ts = parse_ts(s.get("q"))
        if not ts or now - ts > FRESH_MS:
            continue
        state = str(s.get("f") or "Unknown")
        state_stats[state] = state_stats.get(state, 0) + 1
        stations.append({
            "id": str(s.get("a") or ""),
            "name": str(s.get("b") or ""),
            "lat": num(s.get("c")),
            "lon": num(s.get("d")),
            "district": str(s.get("e") or ""),
            "state": state,
            "river": str(s.get("g") or ""),
            "basin": str(s.get("h") or ""),
            "type": str(s.get("i") or ""),
            "level": num(s.get("m")),
            "dangerLevel": num(s.get("o")),
            "margin": num(s.get("p")),
            "status": status,
            "trend": trend,
            "ts": ts,
            "updated": updated,
        })

    out = {
        "updated": updated,
        "at_risk": len(stations),
        "states": [{"state": k, "count": v}
                   for k, v in sorted(state_stats.items(), key=lambda x: -x[1])],
        "stations": stations,
    }
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=1)
    print(f"flood: wrote {len(stations)} at-risk stations -> {OUT} "
          f"(states {len(state_stats)})")


if __name__ == "__main__":
    main()
