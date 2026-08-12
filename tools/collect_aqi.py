#!/usr/bin/env python3
"""Collect Open-Meteo air quality for Malaysia's major cities.

The official APIMS feed blocks non-browser clients, so the dashboard uses
Open-Meteo's keyless air-quality model. The Worker previously made 18 upstream
requests on every /api/aqi call; this collector moves that fan-out to a
GitHub Action and stores the slim result under KV key "aqi".

Run:   python3 tools/collect_aqi.py
Writes: public/aqi.json
Pushes: KV key "aqi" (via kv_upload.py push aqi)
"""

import concurrent.futures
import json
import os
import sys
import time
import urllib.parse
import urllib.request

UA = "mygov-dashboard/1.0 (+https://mygov.faizalmzain.com)"
BASE = "https://air-quality-api.open-meteo.com/v1/air-quality"
OUT = os.environ.get("AQI_OUT", "public/aqi.json")

# Keep in sync with the Worker's /api/aqi CITIES list.
CITIES = [
    ("Kuala Lumpur", 3.1390, 101.6869),
    ("Petaling Jaya", 3.1073, 101.6067),
    ("Shah Alam", 3.0733, 101.5185),
    ("Putrajaya", 2.9264, 101.6964),
    ("Penang", 5.4141, 100.3288),
    ("Johor Bahru", 1.4927, 103.7414),
    ("Ipoh", 4.5975, 101.0901),
    ("Kuching", 1.5535, 110.3593),
    ("Kota Kinabalu", 5.9804, 116.0735),
    ("Melaka", 2.1896, 102.2501),
    ("Kuantan", 3.8077, 103.3260),
    ("Seremban", 2.7246, 101.9343),
    ("Alor Setar", 6.1244, 100.3678),
    ("Kota Bharu", 6.1256, 102.2383),
    ("Kuala Terengganu", 5.3302, 103.1408),
    ("Miri", 4.3993, 113.9914),
    ("Bintulu", 3.1733, 113.0335),
    ("Langkawi", 6.3508, 99.8039),
]


def fetch_city(name, lat, lon):
    q = urllib.parse.urlencode({
        "latitude": lat,
        "longitude": lon,
        "current": "us_aqi,pm2_5",
        "timezone": "Asia/Kuala_Lumpur",
    })
    req = urllib.request.Request(f"{BASE}?{q}", headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=30) as r:
        d = json.loads(r.read().decode("utf-8", "replace"))
    cur = d.get("current") or {}
    aqi = cur.get("us_aqi")
    if aqi is None:
        return None
    pm25 = cur.get("pm2_5")
    return {
        "name": name,
        "aqi": int(round(float(aqi))),
        "pm25": None if pm25 is None else f"{float(pm25):.1f}",
        "time": cur.get("time") or None,
    }


def main():
    stations = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=6) as pool:
        futures = {pool.submit(fetch_city, *c): c for c in CITIES}
        for fut in concurrent.futures.as_completed(futures):
            city = futures[fut]
            try:
                st = fut.result()
            except Exception as e:
                sys.stderr.write(f"AQI {city[0]}: FAILED ({e})\n")
                continue
            if st:
                stations.append(st)

    if not stations:
        sys.exit("aqi: no city readings collected")

    stations.sort(key=lambda s: s["aqi"], reverse=True)
    out = {
        "updated": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "reading_time": stations[0]["time"],
        "stations": stations,
        "worst": stations[0],
        "cleanest": stations[-1],
    }
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=1)
    print(f"aqi: wrote {len(stations)} stations -> {OUT} "
          f"(worst {stations[0]['name']} {stations[0]['aqi']}, "
          f"cleanest {stations[-1]['name']} {stations[-1]['aqi']})")


if __name__ == "__main__":
    main()
