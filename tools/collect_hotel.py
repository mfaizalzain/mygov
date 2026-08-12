#!/usr/bin/env python3
"""Hotel survey collector: quarterly Paid Accommodation Survey (Tourism Malaysia).

The portal (data.tourism.gov.my) publishes a quarterly infographic PDF with
state-level hotel performance: Average Occupancy Rate (AOR), Average Room
Rate (ARR) and hotel guests (domestic/international) for all 16 states, each
with the prior-year comparison. The PDF is a *designed infographic* - no
extractable table - so values are matched to state labels by word
coordinates (pymupdf). Only the LATEST quarter is public (deterministic URL
pattern, newest-first probing, like collect_tourism.py); older quarters sit
behind the portal login and 404.

Writes public/hotel.json -> KV key `hotel`:
  { generated, asOf: {year, quarter, label},
    aor:  [{state, cur, prev}...] sorted desc by cur,
    arr:  [{state, cur, prev}...],
    guests: [{state, dom, intl}...] }

Layout notes (verified against Q1 2026):
- p1 AOR / p2 ARR: vertical lists; each state label sits above its two
  values (cur, prev), values a few px below at similar x. Labels can be
  multi-word ("Negeri Sembilan", "Kuala Lumpur"), so match by label x-RANGE
  (min..max word x) with tolerance, y window below the label.
- p3 guests: HORIZONTAL table - all 16 states in one row (y~598), the
  Domestic values in a row below (y~618), International below that (y~632).
  Match each state to the nearest value in each row by x.

Hard validation gates the write: all 16 states must match with sane ranges,
or the collector keeps the previous file (fail-soft).

Terms: public use, non-commercial, attribution ("Data provided by Tourism
Malaysia"). No LLM anywhere in this pipeline.
"""

import json
import os
import re
import sys
import time
import urllib.error
import urllib.request
from datetime import date

BASE = "https://data.tourism.gov.my/frontend/pdf"
UA = {"User-Agent": "mygov-tourism/1.0 (+https://malaysia-at-a-glance.com)"}

OUT = os.path.join(os.path.dirname(__file__), "..", "public", "hotel.json")

STATES = ["Perlis", "Kedah", "Kelantan", "Pulau Pinang", "Perak", "Selangor",
          "Negeri Sembilan", "Melaka", "Johor", "Pahang", "Terengganu",
          "Putrajaya", "Kuala Lumpur", "Labuan", "Sabah", "Sarawak"]
# Multi-word labels matched as phrases.
MULTI = {"Pulau Pinang", "Negeri Sembilan", "Kuala Lumpur"}

QUARTERS = {1: "Q1", 2: "Q2", 3: "Q3", 4: "Q4"}
QM_START = {1: "Jan", 2: "Apr", 3: "Jul", 4: "Oct"}
QM_END = {1: "Mar", 2: "Jun", 3: "Sep", 4: "Dis"}


def probe(url, timeout=60):
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
    return False


def download(url, timeout=90):
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()


def find_latest():
    """Probe newest->oldest quarters for the latest published hotel survey."""
    idx = date.today().year * 4 + (date.today().month - 1) // 3
    for back in range(8):
        yy = idx // 4
        qq = idx % 4 + 1
        url = f"{BASE}/{yy}/hotel_survey/paid_accommodation/infografik_hotel_{QUARTERS[qq]}_{yy}.pdf"
        if probe(url):
            return (yy, qq, url)
        idx -= 1
    return None


def _words(page):
    """[(x0, y0, text)] sorted by (y, x)."""
    return [(w[0], w[1], w[4]) for w in page.get_text("words")]


def _state_labels(words):
    """Match every state label, returning [(state, x_anchor, y_anchor)].
    Word-based: multi-word states ("Negeri Sembilan") can span two text
    lines (page 3's horizontal table), so the second word is matched by
    proximity (y within 15, x after the first word), not by line joining."""
    found = []
    for st in STATES:
        toks = st.split()
        # get_text() returns words in block order, not visual order - the
        # Top-5 recap block on p2 can precede the main column. Sort by (y, x)
        # so the main column (smaller y) wins.
        hits = sorted(((x, y) for x, y, t in words if t == toks[0]),
                      key=lambda p: (p[1], p[0]))
        for x0, y0 in hits:
            if len(toks) > 1:
                mates = [(x, y) for x, y, t in words
                         if t == toks[1] and abs(y - y0) < 15
                         and abs(x - x0) < 60]
                if not mates:
                    continue
                # anchor on the label CENTER, not the first word - values sit
                # under the middle of a two-word label ("Negeri Sembilan")
                x_anchor = (x0 + mates[0][0]) / 2
            else:
                x_anchor = x0
            if st not in [f[0] for f in found]:
                found.append((st, x_anchor, y0))
            break
    return found


def _match_col(values, x_anchor, y_anchor, x_tol=30, y_win=60):
    """Nearest value word to (x_anchor, y_anchor) within window. Returns word or None."""
    best, best_d = None, None
    for wx, wy, wt in values:
        if abs(wy - y_anchor) > y_win:
            continue
        d = abs(wx - x_anchor)
        if d > x_tol:
            continue
        if best_d is None or d < best_d:
            best, best_d = (wx, wy, wt), d
    return best


def parse_hotel_pdf(pdf_bytes):
    """Extract AOR, ARR and guests by state. Raises ValueError on drift."""
    import fitz  # pymupdf, CI-only dependency

    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    if len(doc) < 3:
        raise ValueError("hotel PDF has fewer than 3 pages - layout drift?")

    def extract_vertical(page, value_re, label):
        """Pages 1-2: vertical state list, two values (cur, prev) below each label."""
        words = _words(page)
        values = [w for w in words if value_re.search(w[2])]
        labels = _state_labels(words)
        if len(labels) != 16:
            raise ValueError(f"{label}: found {len(labels)} state labels, expected 16")
        out = {}
        for st, x_anchor, y in labels:
            # values sit BELOW the label (cur then prev, ~18px apart); the
            # window is one-sided so the state above cannot leak in
            cands = [w for w in values
                     if y < w[1] < y + 75 and abs(w[0] - x_anchor) < 30]
            cands.sort(key=lambda w: (w[1], w[0]))
            if len(cands) < 2:
                raise ValueError(f"{label}: {st} matched {len(cands)} values")
            out[st] = (_num(cands[0][2]), _num(cands[1][2]))
            if not out[st][0] or out[st][0] is None:
                raise ValueError(f"{label}: {st} unparsable {cands[:2]}")
        return out

    # ── page 1: AOR by state (percent) ────────────────────────────────
    aor = extract_vertical(doc[0], re.compile(r"\d+(\.\d+)?\s*%"), "AOR")
    for st, (c, p) in aor.items():
        if c is None or p is None or not (0 <= c <= 100):
            raise ValueError(f"AOR: {st} out of range {aor[st]}")

    # ── page 2: ARR by state (RM) ─────────────────────────────────────
    arr = extract_vertical(doc[1], re.compile(r"RM\s?\d"), "ARR")
    for st, (c, p) in arr.items():
        if c is None or p is None or c > 5000:
            raise ValueError(f"ARR: {st} out of range {arr[st]}")

    # ── page 3: guests by state (horizontal table) ────────────────────
    words3 = _words(doc[2])
    guests_rows = sorted(w for w in words3 if re.fullmatch(r"[\d,]{4,}", w[2]))
    labels3 = _state_labels(words3)
    if len(labels3) != 16:
        raise ValueError(f"guests: found {len(labels3)} state labels, expected 16")
    # The two value rows: domestic y and international y = the two most common y's
    ys = {}
    for _, y, t in guests_rows:
        ys[round(y)] = ys.get(round(y), 0) + 1
    rows = sorted(((y, n) for y, n in ys.items() if n >= 14), key=lambda r: -r[1])
    if len(rows) < 2:
        raise ValueError(f"guests: value rows not found {ys}")
    y_dom, y_intl = rows[0][0], rows[1][0]
    dom_row = [w for w in guests_rows if abs(w[1] - y_dom) < 3]
    intl_row = [w for w in guests_rows if abs(w[1] - y_intl) < 3]
    guests = {}
    for st, x_anchor, y in labels3:
        d = _match_col(dom_row, x_anchor, y_dom, x_tol=28)
        it = _match_col(intl_row, x_anchor, y_intl, x_tol=28)
        if not d or not it:
            raise ValueError(f"guests: {st} missing dom/intl value")
        guests[st] = (_num(d[2]), _num(it[2]))
        if not guests[st][0] or guests[st][0] < 100:
            raise ValueError(f"guests: {st} implausible {guests[st]}")

    # Cross-check: the 16 states must sum to the national total printed on
    # the page (23,844,637 for Q1 2026). Guards against a silent row swap.
    nat = [w for w in words3 if re.fullmatch(r"[\d,]{7,}", w[2])
           and w[1] > 200 and w[1] < 250]
    if len(nat) >= 1:
        national = _num(nat[0][2])
        total = sum(v[0] + v[1] for v in guests.values())
        if national and abs(total - national) / national > 0.001:
            raise ValueError(f"guests: state sum {total:,.0f} != national "
                             f"{national:,.0f}")

    return {"aor": aor, "arr": arr, "guests": guests}


def _num(s):
    s = re.sub(r"[^0-9.]", "", s or "")
    try:
        return float(s)
    except ValueError:
        return None


def main():
    latest = find_latest()
    if not latest:
        sys.stderr.write("hotel: no latest quarter found (not published yet?)\n")
        return 0
    year, quarter, url = latest
    label = f"{QM_START[quarter]}–{QM_END[quarter]} {year}"
    try:
        data = parse_hotel_pdf(download(url))
    except Exception as e:
        sys.stderr.write(f"hotel: parse failed, keeping previous file: {e}\n")
        return 1

    def by_state(block, key):
        return [{"state": st, "cur": v[0], "prev": v[1]}
                for st, v in sorted(block[key].items(),
                                    key=lambda kv: -(kv[1][0] or 0))]

    out = {
        "generated": date.today().isoformat(),
        "asOf": {"year": year, "quarter": quarter, "label": label},
        "source": "Tourism Malaysia Paid Accommodation Survey",
        "aor": by_state(data, "aor"),
        "arr": by_state(data, "arr"),
        "guests": [{"state": st, "dom": v[0], "intl": v[1]}
                   for st, v in sorted(data["guests"].items(),
                                      key=lambda kv: -(kv[1][0] + kv[1][1]))],
    }
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(out, f, separators=(",", ":"), ensure_ascii=False)
    sys.stderr.write(f"hotel: wrote {OUT} ({len(open(OUT).read()):,} bytes, "
                     f"{len(out['aor'])} states, {label})\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
