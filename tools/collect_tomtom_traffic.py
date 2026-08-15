#!/usr/bin/env python3
"""Collect live TomTom Traffic Incidents for Malaysian regions into one KV-ready JSON.

Why this source: the InfoTrafikGZ Telegram channel (collect_traffic.py) reports
almost exclusively HIGHWAY traffic (PLUS, MEX, KESAS...). City/urban streets and
popular-destination towns are invisible to it. TomTom's Traffic Incident Details
API (v5) fills that gap: structured incidents (accidents, closures, roadworks)
with coordinates, road names, start/end times - for any bounding box.

Regions are chosen to complement (not duplicate) the highway Telegram feed:
  - kl-selangor   : Klang Valley urban core + suburbs (excludes most highways)
  - johor         : JB city + Iskandar + Pasir Gudang / Kulai / Pontian
  - penang        : George Town + Butterworth + Seberang Perai (incl. Permatang)
  - perak-ipoh    : Ipoh city + Gopeng / Batu Gajah / Lumut
  - melaka        : Melaka city + Ayer Keroh / Tanjung Kling / Sungai Udang
  - pahang-cameron: Cameron Highlands (Ringlet, Tanah Rata, Brinchang)
  - kedah-langkawi: Langkawi island
  - kuantan       : Kuantan city + Gambang / Balok
  - kelantan-kb   : Kota Bharu + Wakaf Bharu / Pengkalan Chepa
  - kuching       : Kuching city + Matang / Batu Kawa (Borneo)

Bounding boxes were validated against live API responses on 2026-08-15; each
returns 2-552 incidents at peak. Exact-match lon/lat ordering (sw,ne).

Output shape (KV key "traffic_incidents"):
{
  "updated": "2026-08-15T12:00:00Z",
  "source": "https://developer.tomtom.com/traffic-api",
  "regions": {
    "kl-selangor": {
      "bbox": [101.45, 2.95, 101.85, 3.35],
      "name": "Klang Valley",
      "incidents": [
        {
          "cat": 6, "catName": "Accident",
          "from": "Bandar Bukit Raja", "to": "Bandar Bukit Raja",
          "start": "2026-08-15T10:08:00Z", "end": "2026-08-15T10:56:00Z",
          "roads": ["3217"],
          "delay": 2, "events": ["Queuing traffic"],
          "lat": 3.08898, "lon": 101.44934,
          "polyline": [[101.44934,3.08898],[101.45055,3.08898]]
        }, ...
      ]
    }, ...
  },
  "total": 552,
  "byCat": {"Accident": 486, "Road closure": 34, "Roadworks": 32}
}

Only incident categories that matter to drivers are kept (accidents, closures,
roadworks, hazards, congestion). Planned future incidents are excluded
(timeValidityFilter=present). Lat/lon is the FIRST point of the LineString so
the frontend can drop a marker without decoding polylines. `events` carries
TomTom's per-incident descriptions ("Stationary traffic", "Closed", ...);
`delay` is magnitudeOfDelay (0=unknown .. 4=extreme).
"""

import json
import os
import sys
import time
import urllib.request

KEY = os.environ.get("TOMTOM_API_KEY", "")
BASE = "https://api.tomtom.com/traffic/services/5/incidentDetails"
# lon,lat sw -> lon,lat ne  (validated against live API, 2026-08-15)
REGIONS = [
    ("kl-selangor", "Klang Valley",
     [101.45, 2.95, 101.85, 3.35]),
    ("johor", "Johor Bahru",
     [103.55, 1.40, 103.95, 1.65]),
    ("penang", "Penang",
     [100.20, 5.20, 100.55, 5.55]),
    ("perak-ipoh", "Ipoh",
     [101.00, 4.50, 101.20, 4.70]),
    ("melaka", "Melaka",
     [102.15, 2.10, 102.45, 2.35]),
    ("pahang-cameron", "Cameron Highlands",
     [101.30, 4.35, 101.55, 4.60]),
    ("kedah-langkawi", "Langkawi",
     [99.70, 6.20, 99.95, 6.45]),
    ("kuantan", "Kuantan",
     [103.20, 3.70, 103.50, 4.00]),
    ("kelantan-kb", "Kota Bharu",
     [102.20, 6.00, 102.50, 6.20]),
    ("kuching", "Kuching",
     [110.20, 1.40, 110.55, 1.70]),
]
MAX_INCIDENTS = int(os.environ.get("TOMMAX_INCIDENTS", "800"))
UA = "mygov-dashboard/1.0 (+https://mygov.faizalmzain.com)"

# iconCategory -> friendly name (TomTom incident category taxonomy)
CATS = {
    0: "Unknown", 1: "Accident", 2: "Fog", 3: "Dangerous conditions",
    4: "Rain", 5: "Ice", 6: "Accident", 7: "Road closed", 8: "Road works",
    9: "Hazard", 10: "Jam", 11: "Lane closed", 12: "Road blocked",
    13: "Road works", 14: "Road blocked", 15: "Weather",
    16: "Flooding", 17: "Detour", 18: "Cluster", 19: "Broken down vehicle",
}
# Keep only driver-relevant categories (accidents, closures, works, hazards,
# jams, flooding, breakdowns, lane closures). Skip fog/ice/weather noise.
KEEP_CATS = {1, 3, 6, 7, 8, 9, 10, 11, 12, 13, 14, 16, 18, 19}


def fetch_region(bbox):
    """Fetch incidents in a bbox; returns list of incidents (slimmed) or [] on error."""
    b = ",".join(f"{x:.5f}" for x in bbox)
    fields = "{incidents{type,geometry{type,coordinates},properties{iconCategory,magnitudeOfDelay,startTime,endTime,from,to,roadNumbers,events{description,code}}}}"
    u = (f"{BASE}?key={KEY}&bbox={b}&fields={fields}"
         f"&language=en-GB&t=1111&timeValidityFilter=present")
    req = urllib.request.Request(u, headers={"user-agent": UA})
    with urllib.request.urlopen(req, timeout=45) as r:
        return json.loads(r.read().decode("utf-8", "replace")).get("incidents", [])


def slim(inc):
    """Reduce one TomTom incident to the fields the dashboard needs."""
    p = inc.get("properties", {})
    g = inc.get("geometry", {})
    coords = g.get("coordinates") or []
    lat, lon = None, None
    if coords:
        # coords are [lon, lat] pairs
        lon, lat = coords[0][0], coords[0][1]
    return {
        "cat": p.get("iconCategory"),
        "catName": CATS.get(p.get("iconCategory"), "Unknown"),
        "from": p.get("from", ""),
        "to": p.get("to", ""),
        "start": p.get("startTime", ""),
        "end": p.get("endTime", ""),
        "roads": p.get("roadNumbers") or [],
        "delay": p.get("magnitudeOfDelay"),
        "events": [e.get("description", "") for e in p.get("events", []) if e.get("description")],
        "lat": lat,
        "lon": lon,
        "polyline": [[c[0], c[1]] for c in coords[:50]],  # cap size
    }


def main():
    if not KEY:
        sys.exit("tomtom: TOMTOM_API_KEY not set")
    out_regions = {}
    total = 0
    by_cat = {}
    for slug, name, bbox in REGIONS:
        try:
            incs = fetch_region(bbox)
        except Exception as e:
            sys.stderr.write(f"tomtom: {slug} fetch failed: {e}\n")
            incs = []
        kept = [slim(i) for i in incs if i.get("properties", {}).get("iconCategory") in KEEP_CATS]
        kept = kept[:MAX_INCIDENTS]
        out_regions[slug] = {
            "bbox": bbox,
            "name": name,
            "incidents": kept,
        }
        total += len(kept)
        for i in kept:
            by_cat[i["catName"]] = by_cat.get(i["catName"], 0) + 1
        print(f"tomtom: {slug}: {len(incs)} raw -> {len(kept)} kept")
        time.sleep(0.3)  # be gentle; 10 regions per run

    out = {
        "updated": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "source": "https://developer.tomtom.com/traffic-api",
        "note": "TomTom Traffic Incidents v5. Structured incidents (accidents, closures, "
                "roadworks) for urban + popular-destination areas; the InfoTrafikGZ "
                "Telegram feed covers highways.",
        "regions": out_regions,
        "total": total,
        "byCat": by_cat,
    }
    dest = os.environ.get("TRAFFIC_INC_OUT", "public/traffic_incidents.json")
    with open(dest, "w", encoding="utf-8") as fh:
        json.dump(out, fh, ensure_ascii=False)
    print(f"tomtom: {total} incidents -> {dest} ({len(by_cat)} categories)")


if __name__ == "__main__":
    main()
