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


def fetch_all_cities():
    lats = ",".join(str(c[1]) for c in CITIES)
    lons = ",".join(str(c[2]) for c in CITIES)
    q = urllib.parse.urlencode({
        "latitude": lats,
        "longitude": lons,
        "current": "us_aqi,pm2_5",
        "timezone": "Asia/Kuala_Lumpur",
    })
    req = urllib.request.Request(f"{BASE}?{q}", headers={"User-Agent": UA})
    ctx = None
    try:
        import ssl
        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
    except Exception:
        pass
    with urllib.request.urlopen(req, context=ctx, timeout=30) as r:
        raw = json.loads(r.read().decode("utf-8", "replace"))

    items = raw if isinstance(raw, list) else [raw]
    stations = []
    for (name, _lat, _lon), item in zip(CITIES, items):
        cur = item.get("current") or {}
        aqi = cur.get("us_aqi")
        if aqi is None:
            continue
        pm25 = cur.get("pm2_5")
        stations.append({
            "name": name,
            "aqi": int(round(float(aqi))),
            "pm25": None if pm25 is None else f"{float(pm25):.1f}",
            "time": cur.get("time") or None,
        })
    return stations


def main():
    try:
        stations = fetch_all_cities()
    except Exception as e:
        sys.exit(f"aqi: batch fetch failed ({e})")

    if not stations:
        sys.exit("aqi: no city readings collected")

    stations.sort(key=lambda s: s["aqi"], reverse=True)
    out = {
        "updated": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "reading_time": stations[0]["time"] if stations[0].get("time") else None,
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
