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
      "ok": true,          // false = this region's fetch failed, NOT "clear"
      "total": 132,        // after dedupe, before the per-region cap
      "incidents": [
        {
          "cat": 6, "catName": "Jam",
          "from": "Bandar Bukit Raja", "to": "Bandar Bukit Raja",
          "start": "2026-08-15T10:08:00Z", "end": "2026-08-15T10:56:00Z",
          "roads": ["3217"],
          "delay": 2, "events": ["Queuing traffic"],
          "lat": 3.08898, "lon": 101.44934
        }, ...
      ]
    }, ...
  },
  "total": 552,
  "byCat": {"Jam": 486, "Road closed": 34, "Road works": 32}
}

Only incident categories that matter to drivers are kept (accidents, closures,
roadworks, jams, flooding, breakdowns). Planned future incidents are excluded
(timeValidityFilter=present). Duplicates of one jam across adjacent road
segments are collapsed, what survives is sorted worst-first, and each region is
capped - the whole file is fetched by every visitor. Lat/lon is the FIRST point
of the LineString, and is what the frontend matches against a visitor's
coordinates to pick their region. `events` carries TomTom's per-incident
descriptions ("Stationary traffic", "Closed", ...); `delay` is
magnitudeOfDelay (0=unknown, 1=minor, 2=moderate, 3=major, 4=undefined -
which is what closures carry, not "extreme").
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

# iconCategory -> friendly name. This is TomTom's published Traffic Incident
# Details v5 taxonomy, not a guess: an earlier hand-written map here had it
# shifted, so 875 of 1,084 ordinary jams were being served to the dashboard
# labelled "Accident" (and every road closure as "Road works"). The incidents'
# own `events` text is the giveaway - category 6 always reads "Stationary
# traffic"/"Queuing traffic". There is no 12, 13, 15 or 16 in the enum.
CATS = {
    0: "Unknown", 1: "Accident", 2: "Fog", 3: "Dangerous conditions",
    4: "Rain", 5: "Ice", 6: "Jam", 7: "Lane closed", 8: "Road closed",
    9: "Road works", 10: "Wind", 11: "Flooding", 14: "Broken down vehicle",
}
# Keep only what changes a driver's route: accidents, closures, roadworks,
# jams, flooding and breakdowns. Fog/rain/ice/wind (2, 4, 5, 10) are weather,
# which the dashboard already covers properly, and 0 is unknown.
KEEP_CATS = {1, 3, 6, 7, 8, 9, 11, 14}
# Worst-first ordering for the per-region cap below. A blocked road matters
# more than a slow one no matter what delay magnitude rides with it, and
# magnitudeOfDelay cannot express that: 4 means "undefined", which is what
# closures carry, so sorting on delay alone puts closures in the same bucket
# as unknowns.
# Jams outrank roadworks. This was the other way round at first, which read
# sensibly as "severity" and was wrong for a live ticker: roadworks are
# semi-permanent - the same B27 layout is there for weeks - while a jam is the
# thing happening now. Measured 15 Aug 2026 at 22:45 MYT, Klang Valley shipped
# 19 active roadworks and 21 jams that had already ended, so the ticker was
# 100% roadworks; at peak the roadworks were still taking the top slots out of
# 388 candidates. Closures, accidents and flooding stay above both.
CAT_RANK = {8: 0, 7: 1, 1: 2, 11: 3, 3: 4, 14: 5, 6: 6, 9: 7}
# ...and even ranked last they can crowd a region out, because there are simply
# a lot of them and they never expire. At most this fraction of a region's
# slots goes to roadworks; the rest is held for incidents that are live.
ROADWORKS_SHARE = 3
# Only the first N of each region survive, worst-first. The frontend shows at
# most a handful in the ticker, and the whole file is fetched by every visitor
# on every load - 1,084 incidents with polylines was 905 KB of payload to
# render six lines of text.
PER_REGION = int(os.environ.get("TOMTOM_PER_REGION", "40"))


def fetch_region(bbox):
    """Fetch incidents in a bbox. Raises on failure; retried by the caller.

    `t` (trafficModelID) is deliberately absent: it defaults to the current
    model, which is what a live dashboard wants. It used to be pinned to a
    literal 1111 - a model id is only valid for two minutes before it times
    out, so pinning one asks for a stale or rejected response.
    """
    b = ",".join(f"{x:.5f}" for x in bbox)
    fields = "{incidents{type,geometry{type,coordinates},properties{iconCategory,magnitudeOfDelay,startTime,endTime,from,to,roadNumbers,events{description,code}}}}"
    u = (f"{BASE}?key={KEY}&bbox={b}&fields={fields}"
         f"&language=en-GB&timeValidityFilter=present")
    req = urllib.request.Request(u, headers={"user-agent": UA})
    with urllib.request.urlopen(req, timeout=45) as r:
        return json.loads(r.read().decode("utf-8", "replace")).get("incidents", [])


def fetch_region_retry(slug, bbox, tries=3):
    """fetch_region with backoff. Returns (incidents, ok).

    ok=False is not the same as "no incidents": a region that failed must not
    read on the dashboard as a region that is clear, so the flag is carried
    through to the JSON.
    """
    for n in range(tries):
        try:
            return fetch_region(bbox), True
        except Exception as e:
            sys.stderr.write(f"tomtom: {slug} fetch failed (try {n + 1}/{tries}): {e}\n")
            if n + 1 < tries:
                time.sleep(2 ** n)
    return [], False


def slim(inc):
    """Reduce one TomTom incident to the fields the dashboard needs.

    No polyline. The frontend has never drawn one - it renders a line of text
    per incident - and at up to 50 coordinate pairs each they were ~90% of the
    file. lat/lon stay: they are what lets the frontend pick the region the
    visitor is actually in.
    """
    p = inc.get("properties", {})
    coords = (inc.get("geometry") or {}).get("coordinates") or []
    lat, lon = None, None
    if coords:
        # coords are [lon, lat] pairs
        lon, lat = round(coords[0][0], 5), round(coords[0][1], 5)
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
    }


def dedupe(incs):
    """One jam reported on six adjacent segments is one jam.

    TomTom returns an incident per road segment, so a single stretch of
    stationary traffic on the Federal Highway arrives as a dozen identical
    "Bandar Bukit Raja -> Bandar Bukit Raja - Stationary traffic" rows. Keyed
    on category + endpoints + lead event, which collapses those without
    merging two genuinely different incidents on the same road.
    """
    seen, out = set(), []
    for i in incs:
        # Unordered endpoints: a closure is reported once per direction, as
        # "A -> B" and "B -> A". Those are one closed road, not two.
        k = (i["cat"], frozenset((i["from"], i["to"])), (i["events"] or [""])[0])
        if k in seen:
            continue
        seen.add(k)
        out.append(i)
    return out


def severity(i):
    """Sort key: worst first, arterials before back streets.

    Category alone is not enough. Sorting purely on it filled the ticker with
    six consecutive closures of unnamed housing-estate lanes (Jalan Putra
    Harmoni 1/3D, 1/3E, 1/3F...) while a jam on the Federal Highway sat below
    them. A road number is the available proxy for "a road people are
    actually on", so it leads. Delay cannot break these ties: closures all
    carry magnitudeOfDelay 4, which means undefined, not extreme.
    """
    d = i.get("delay")
    d = d if isinstance(d, int) else 0
    return (0 if i.get("roads") else 1,
            CAT_RANK.get(i.get("cat"), 9),
            -(d if d != 4 else 3))


def take(kept, limit):
    """Fill a region's slots worst-first, holding some back from roadworks.

    Roadworks never expire, so on rank alone they can fill a region and leave
    nothing for the incidents a driver is actually deciding around. They get at
    most limit/ROADWORKS_SHARE slots - unless there is nothing else to fill
    with, in which case the spill takes the remainder rather than shipping a
    half-empty region.
    """
    cap = max(1, limit // ROADWORKS_SHARE)
    out, spill, used = [], [], 0
    for i in kept:
        if len(out) >= limit:
            break
        if i.get("cat") == 9:          # Road works
            if used >= cap:
                spill.append(i)
                continue
            used += 1
        out.append(i)
    for i in spill:
        if len(out) >= limit:
            break
        out.append(i)
    return out


def main():
    if not KEY:
        sys.exit("tomtom: TOMTOM_API_KEY not set")
    out_regions = {}
    total = 0
    by_cat = {}
    for slug, name, bbox in REGIONS:
        incs, ok = fetch_region_retry(slug, bbox)
        kept = [slim(i) for i in incs[:MAX_INCIDENTS]
                if i.get("properties", {}).get("iconCategory") in KEEP_CATS]
        kept = dedupe(kept)
        kept.sort(key=severity)
        for i in kept:
            by_cat[i["catName"]] = by_cat.get(i["catName"], 0) + 1
        out_regions[slug] = {
            "bbox": bbox,
            "name": name,
            "ok": ok,
            # Count before the cap, so the dashboard can say "40 of 132"
            # rather than implying the region only has what it was sent.
            "total": len(kept),
            "incidents": take(kept, PER_REGION),
        }
        total += len(kept)
        print(f"tomtom: {slug}: {len(incs)} raw -> {len(kept)} kept "
              f"-> {len(out_regions[slug]['incidents'])} sent"
              f"{'' if ok else ' (FETCH FAILED)'}")
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
