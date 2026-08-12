#!/usr/bin/env python3
"""Collect every Malaysia Airports FIDS board into one KV-ready JSON.

Why a collector at all: api.myairports.com.my rate-limits Cloudflare
Worker egress IPs (429 on shared egress) even though the API is public
(x-api-key is embedded in the myairports JS bundle). GitHub Actions run
from GitHub's IP pool, which is not rate-limited - the same pattern as
the jina reader for myRapid.

The dashboard fetches /api/fids?code=A|D&terminal=<airport> for 13
airports; the Worker serves the matching board from this file when
present and falls back to a live upstream fetch otherwise.

Output shape (KV key "fids"):
{
  "updated": "2026-08-12T10:00:00Z",
  "boards": { "A|KLIA": { "count": 299, "flights": [...] }, ... }
}
"""

import json
import os
import sys
import time
import urllib.request

KEY = os.environ.get("FIDS_API_KEY", "f02f252a781a4db584d1ae9fce22bed1")
BASE = "https://api.myairports.com.my/passenger-fids/api/flights/search-flights"
PAGE = 200
MAX_PAGES = 6
# 13 airports, arrivals + departures
AIRPORTS = ["KLIA", "klia2", "SZB", "PEN", "BKI", "KCH", "LGK", "KBR",
            "TWU", "AOR", "TGG", "LBU", "IPH"]
CODES = ["A", "D"]
UA = "mygov-dashboard/1.0 (+https://mygov.faizalmzain.com)"


def fetch(code, terminal):
    """Page through one board; return (count, slim_flights) or None on error."""
    def page(skip):
        u = (f"{BASE}?code={code}&key=all&terminal={terminal}&dayKey=0"
             f"&live=true&skip={skip}&take={PAGE}")
        req = urllib.request.Request(u, headers={
            "x-api-key": KEY, "accept": "application/json", "user-agent": UA})
        with urllib.request.urlopen(req, timeout=45) as r:
            return json.loads(r.read().decode("utf-8", "replace"))

    try:
        first = page(0)
    except Exception:
        return None
    statuses = list(first.get("flightStatuses") or [])
    total = int(first.get("count") or len(statuses))
    if statuses and total > len(statuses):
        pages = min((total + PAGE - 1) // PAGE, MAX_PAGES)
        for i in range(1, pages):
            try:
                p = page(i * PAGE)
            except Exception:
                continue
            statuses.extend(p.get("flightStatuses") or [])
    slim = []
    for f in statuses:
        slim.append({
            "flightNumber": f.get("flightNumber"),
            "airline": (f.get("airline") or {}).get("name") or f.get("name") or "",
            "aircraftOperator": f.get("aircraftOperator"),
            "origin": (f.get("origin") or {}).get("city"),
            "destination": (f.get("destination") or {}).get("city"),
            "scheduled": f.get("scheduledTime") or f.get("flightTime"),
            "status": f.get("status") or "",
            "statusCode": f.get("statusCode") or "",
            "gate": (f.get("gate") or {}).get("name"),
            "belt": (f.get("belt") or {}).get("name"),
            "terminal": f.get("terminal"),
            "codeshares": [c.get("flightNumber") for c in (f.get("codeShareFlights") or [])],
        })
    return total, slim


def main():
    boards = {}
    fails = 0
    for code in CODES:
        for apt in AIRPORTS:
            res = fetch(code, apt)
            key = f"{code}|{apt}"
            if res is None:
                sys.stderr.write(f"FIDS {key}: FAILED\n")
                fails += 1
                continue
            total, slim = res
            boards[key] = {"count": total, "flights": slim}
            sys.stderr.write(f"FIDS {key}: {len(slim)}/{total}\n")
            time.sleep(0.5)
    if not boards:
        sys.exit("all FIDS boards failed")
    out = {
        "updated": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "boards": boards,
        "note": "Collected from api.myairports.com.my (public x-api-key). "
                "Served by the dashboard Worker from KV; live fetch is the fallback.",
    }
    dest = os.environ.get("FIDS_OUT", "public/fids.json")
    with open(dest, "w", encoding="utf-8") as fh:
        json.dump(out, fh, ensure_ascii=False)
    print(f"fids: wrote {len(boards)} boards ({fails} failed) to {dest}")


if __name__ == "__main__":
    main()
