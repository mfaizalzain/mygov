"""Tourism arrivals collector: monthly visitor-arrivals PDFs from data.tourism.gov.my.

Tourism Malaysia publishes a monthly top-51 visitor-arrivals table as a PDF.
The files are auth-free (200 without any cookie; login only reveals the
index, whose URLs are deterministic). This collector pattern-probes the
URLs newest-first, downloads the latest published month, extracts the table
with pymupdf's coordinate-aware find_tables() and writes public/tourism.json
-> KV key `tourism`.

Terms (verified 2026-08-11): public use, non-commercial, attribution
("Data provided by Tourism Malaysia"). No LLM anywhere in this pipeline.

URL patterns:
  2026+  visitor:     /frontend/pdf/{year}/visitor_arrivals/top_51_{m}_{year}_visitor.pdf
  2026+  tourist:     /frontend/pdf/{year}/tourist_arrivals/top_51_{m}_{year}_tourist.pdf
  2026+  excursionist:/frontend/pdf/{year}/excursionist_arrivals/Top_51_{m}_{year}_excursionist.pdf (capital T!)
  2014-2025 archive:  /frontend/pdf/{year}/tourist_arrivals/{n}_top_45_tourist_arrivals_{month}_{year}.pdf

Months are Malay abbreviations: jan feb mac apr mei jun jul ogo sep okt nov dis
(March = mac, NOT mar; August = ogo, NOT ogos).
"""

import json
import os
import re
import sys
import urllib.request
import urllib.error
from datetime import date, timedelta

BASE = "https://data.tourism.gov.my/frontend/pdf"
UA = {"User-Agent": "mygov-tourism/1.0 (+https://mygov.faizalmzain.com)"}

MONTHS = ["jan", "feb", "mac", "apr", "may", "jun", "jul", "ogo", "sep", "okt", "nov", "dis"]
# Filename month slugs: all Malay abbreviations EXCEPT May, which is the
# English 'may' (verified by probing 2026-08-11: jan feb mac apr may return
# 200; mei returns 404). March = mac, August = ogo.
FULL_MONTHS = ["january", "february", "march", "april", "may", "june",
               "july", "august", "september", "october", "november", "december"]

OUT = os.path.join(os.path.dirname(__file__), "..", "public", "tourism.json")


def malay_to_num(m):
    return MONTHS.index(m) + 1 if m in MONTHS else None


def month_label(y, m):
    """'May 2026' from (2026, 5)."""
    return f"{FULL_MONTHS[m - 1].capitalize()} {y}"


def probe(url, timeout=60):
    """HEAD-like GET probe: returns True on 200, False on 404. Retries
    transient errors 3x with backoff; a definitive 404 is 'not published'."""
    for i, wait in enumerate([0, 5, 10]):
        try:
            req = urllib.request.Request(url, headers=UA, method="GET")
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return r.status == 200
        except urllib.error.HTTPError as e:
            if e.code == 404:
                return False
            if i == 2:
                return False
        except Exception:
            if i == 2:
                return False
        time.sleep(wait)


def download(url, timeout=90):
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()


def find_latest():
    """Probe newest->oldest for the latest published visitor PDF.
    Returns (year, month_num, url) or None."""
    today = date.today()
    # Current year, visitor pattern, from this month back ~4 months
    for back in range(0, 4):
        d = today - timedelta(days=30 * back)
        y, m = d.year, MONTHS[d.month - 1]
        url = f"{BASE}/{y}/visitor_arrivals/top_51_{m}_{y}_visitor.pdf"
        if probe(url):
            return (y, d.month, url)
    # Previous year, archive pattern
    for y in (today.year - 1, today.year - 2):
        for m in reversed(FULL_MONTHS):
            n = FULL_MONTHS.index(m) + 1
            url = f"{BASE}/{y}/tourist_arrivals/{n}_top_45_tourist_arrivals_{m}_{y}.pdf"
            if probe(url):
                return (y, n, url)
    return None


def parse_visitor_pdf(pdf_bytes):
    """Extract the top-51 table via pymupdf find_tables().
    Returns dict: {generated, asOf, totals, visitor, tourist, excursionist}."""
    import fitz  # pymupdf, CI-only dependency (like pandas for pricecatcher)

    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    page = doc[0]
    tables = page.find_tables()
    if not tables.tables:
        raise ValueError("no table found in tourism PDF")
    data = tables.tables[0].extract()

    rows = []
    for r in data:
        rank = (r[0] or "").strip()
        if not re.fullmatch(r"\d{1,2}", rank):
            continue
        country = (r[1] or "").strip().title()
        if not country:
            continue
        vals = [_num(r[i]) for i in range(2, 14)]
        if all(v is None for v in vals):
            continue
        rows.append({
            "rank": int(rank), "country": country,
            "prev": vals[0], "cur": vals[1], "y2025": vals[2], "y2019": vals[3],
            "g_mom": vals[4], "g_yoy": vals[5], "g_2019": vals[6],
            "ytd26": vals[7], "ytd25": vals[8], "ytd19": vals[9],
            "gy_yoy": vals[10], "gy_2019": vals[11],
        })
    if len(rows) < 50:
        raise ValueError(f"only {len(rows)} rows parsed - layout drift?")

    totals = None
    for r in data:
        if (r[0] or "").strip().upper() == "GRAND TOTAL":
            vals = [_num(r[i]) for i in range(2, 14)]
            totals = {
                "prev": vals[0], "cur": vals[1], "y2025": vals[2], "y2019": vals[3],
                "g_mom": vals[4], "g_yoy": vals[5], "g_2019": vals[6],
                "ytd26": vals[7], "ytd25": vals[8], "ytd19": vals[9],
                "gy_yoy": vals[10], "gy_2019": vals[11],
            }
            break
    return rows, totals


def _num(s):
    if s is None:
        return None
    s = str(s).replace(",", "").strip()
    if not s or s in ("-", "--", "n/a"):
        return None
    neg = s.startswith("(") and s.endswith(")")
    s = s.strip("()")
    try:
        f = float(s)
    except ValueError:
        return None
    if neg:
        f = -f
    return int(f) if f == int(f) else round(f, 1)


def collect(dry_run=False):
    hit = find_latest()
    if not hit:
        print("no tourism PDF found (not published yet) - keeping existing tourism.json")
        return False
    year, month, url = hit
    pdf = download(url)
    rows, totals = parse_visitor_pdf(pdf)
    out = {
        "generated": date.today().isoformat(),
        "asOf": {"year": year, "month": month, "label": month_label(year, month)},
        "totals": totals,
        "visitor": rows,
    }
    raw = json.dumps(out, ensure_ascii=False)
    if dry_run:
        print(f"resolved: {url}")
        print(f"rows: {len(rows)}, totals: {totals and totals['cur']}, "
              f"size: {len(raw)} bytes")
        return True
    with open(OUT, "w") as f:
        f.write(raw)
    print(f"wrote {OUT} ({len(raw)} bytes): asOf={out['asOf']['label']}, "
          f"visitor={len(rows)} rows, total={totals and totals['cur']}")
    return True


if __name__ == "__main__":
    import time
    collect(dry_run="--dry-run" in sys.argv)
