#!/usr/bin/env python3
"""Collect live Malaysia traffic reports from the InfoTrafikGZ Telegram channel.

Why this source: KL/LLM publish NO public traffic-flow API (researched
2026-08-11 - DBKL only 3 referer-gated cameras, LLM ArcGIS cameras all
internal). The InfoTrafikGZ Telegram channel (t.me/s/InfoTrafikGZ) posts
crowd-sourced live traffic reports in BM around the clock (MEX, MEXII,
LPT, KESAS, PLUS, Puchong, Serdang...). Its public web preview page is
free, keyless, and not rate-limited - a perfect collector source.

Output shape (KV key "traffic"):
{
  "updated": "2026-08-12T12:33:31Z",
  "posts": [
    {"id": 1009699, "ts": 1723444411, "time": "2026-08-12T12:33:31+00:00",
     "text": "1900hrs: Semua lorong berfungsi...", "url": "https://t.me/InfoTrafikGZ/1009699",
     "tags": ["MEX"]},
    ...
  ]
}
Tags are highway/road keywords detected in the text (lowercased, BM).
"""

import html
import json
import os
import re
import sys
import time
import urllib.request

CHANNEL = "InfoTrafikGZ"
PAGE = f"https://t.me/s/{CHANNEL}"
UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15"
MAX_POSTS = int(os.environ.get("TRAFFIC_MAX_POSTS", "60"))

# Highway / road keywords for tags (BM text). Keep broad; the dashboard
# filters by these chips. Order matters: longer/more specific first so
# "MEXII" isn't swallowed by "MEX" - we match word boundaries anyway.
HIGHWAYS = [
    "MEXII", "MEX II", "MEX", "E20", "E30", "E35", "E36", "E38", "E2",
    "NKVE", "LPT", "LPT1", "LPT2", "KESAS", "PLUS", "SKVE", "ELITE", "LEKAS",
    "SPRINT", "DUKE", "AKLEH", "GCE", "SUKE", "DASH", "MRR2", "JKR", "LDP",
    "Jalan Kuching", "Jalan Ampang", "Persiaran", "Puchong", "Serdang",
    "Kajang", "Subang", "Shah Alam", "Klang", "Putrajaya", "Cyberjaya",
    "Bangi", "Gombak", "Rawang", "Setapak", "Cheras", "Ampang", "KLCC",
]
TIME_RE = re.compile(r"(\d{1,2}):(\d{2})")

# Traffic-signal patterns: a post is kept only when the text matches at
# least one (case-insensitive). The channel occasionally posts PSAs and
# general announcements (phone-while-driving reminders etc.) which are
# NOT traffic updates and would pollute the feed.
TRAFFIC_SIGNALS = [
    r"trafik", r"lorong", r"lebuhraya", r"laluan", r"penutupan",
    r"kemalangan", r"sesak", r"km\s*\d", r"\d{3,4}\s*h\b",
]
TRAFFIC_RE = re.compile("|".join(TRAFFIC_SIGNALS), re.I)

# PSA / announcement markers - posts carrying these are safety reminders
# or promos (they still carry the channel's brand footer, so the positive
# signals above alone are not enough). Excluded outright.
PSA_MARKERS = [
    r"#pesan", r"announcement", r"peringatan", r"keselamatan",
    r"nasihat", r"amalan", r"pesanprolintas", r"kempen",
]
PSA_RE = re.compile("|".join(PSA_MARKERS), re.I)

# message block regex - a whole tgme_widget_message_wrap div; the
# data-post id lives on the inner message div, text + time inside it
BLOCK_RE = re.compile(
    r'<div class="tgme_widget_message_wrap[^"]*"[^>]*>.*?'
    r'</div>\s*</div>\s*</div>\s*</div>',
    re.S)
MSG_RE = re.compile(
    r'<div class="tgme_widget_message_text[^>]*>(.*?)</div>.*?'
    r'<time[^>]*datetime="([^"]*)"',
    re.S)
ID_RE = re.compile(r'data-post="[^"]*?/(\d+)"')


def fetch():
    req = urllib.request.Request(PAGE, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=40) as r:
        return r.read().decode("utf-8", "replace")


def clean_text(raw):
    # strip tags, collapse whitespace, unescape entities
    t = re.sub(r"<[^>]+>", " ", raw)
    t = html.unescape(t)
    t = re.sub(r"\s+", " ", t).strip()
    return t


def post_time(iso):
    # 2026-08-12T12:33:31+00:00 -> epoch
    try:
        dt = time.strptime(iso[:19], "%Y-%m-%dT%H:%M:%S")
        return int(time.mktime(dt) - time.timezone + 8 * 3600)  # MYT is +08
    except ValueError:
        return None


def tags_for(text):
    low = text.lower()
    found = []
    for h in HIGHWAYS:
        # word-boundary match, case-insensitive; skip "MEX" inside "MEXII"
        pat = re.compile(r"\b" + re.escape(h.lower()) + r"\b")
        if pat.search(low) and h not in found:
            found.append(h)
    # prefer the canonical form for MEX II / MEXII
    return found


def main():
    try:
        page = fetch()
    except Exception as e:
        sys.exit(f"traffic: fetch failed: {e}")

    posts = []
    seen = set()
    for block in BLOCK_RE.findall(page):
        m = MSG_RE.search(block)
        if not m:
            continue
        raw, iso = m.group(1), m.group(2)
        text = clean_text(raw)
        if not text:
            continue
        # keep only genuine traffic updates, not PSAs / general posts
        if not TRAFFIC_RE.search(text):
            continue
        if PSA_RE.search(text):
            continue
        idm = ID_RE.search(block)
        pid = int(idm.group(1)) if idm else None
        key = (text, iso)
        if key in seen:
            continue
        seen.add(key)
        posts.append({
            "id": pid,
            "ts": post_time(iso),
            "time": iso,
            "text": text,
            "url": f"https://t.me/{CHANNEL}/{pid}" if pid else None,
            "tags": tags_for(text),
        })

    posts.sort(key=lambda p: p["ts"] or 0, reverse=True)
    posts = posts[:MAX_POSTS]
    if not posts:
        sys.exit("traffic: no posts parsed - channel structure may have changed")

    out = {
        "updated": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "source": f"https://t.me/s/{CHANNEL}",
        "note": "Crowd-sourced live traffic reports from the InfoTrafikGZ "
                "Telegram channel. Not an official feed.",
        "posts": posts,
    }
    dest = os.environ.get("TRAFFIC_OUT", "public/traffic.json")
    with open(dest, "w", encoding="utf-8") as fh:
        json.dump(out, fh, ensure_ascii=False)
    print(f"traffic: {len(posts)} posts -> {dest} (tags: "
          f"{sorted({t for p in posts for t in p['tags']})[:12]}...)")


if __name__ == "__main__":
    main()
