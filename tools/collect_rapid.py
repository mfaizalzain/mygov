#!/usr/bin/env python3
"""Latest Rapid KL service alert collector (myrapid.com.my PULSE).

The PULSE alerts page sits behind Incapsula (a JS-challenge WAF), so plain
HTTP - page, RSS, wp-json (which additionally returns 401 rest_forbidden for
anonymous reads) - all fail. The r.jina.ai reader proxy renders the page
server-side and returns clean markdown; we parse the NEWEST alert post
(title, excerpt, MYT timestamp, link) and store it.

Why a collector instead of a live Worker fetch: jina's free tier rate-limits
per source IP, and Cloudflare Worker egress IPs are shared - the Worker fetch
gets throttled to null. GitHub Actions runners use a different pool, so the
10-minute cron below is reliable. The Worker serves the KV copy with a live
fetch as fallback.

Run:   python3 tools/collect_rapid.py
Writes: public/rapid_alerts.json  (committed fallback)
Pushes: KV key "rapid"  (via kv_upload.py push rapid)
"""
import json
import re
import sys
import time
import urllib.request

JINA = "https://r.jina.ai/https://myrapid.com.my/pulse/service-alerts-on-pulse/"
OUT = "public/rapid_alerts.json"
MONTHS = "January|February|March|April|May|June|July|August|September|October|November|December"
MON = {m.lower(): i for i, m in enumerate(
    ["January", "February", "March", "April", "May", "June", "July",
     "August", "September", "October", "November", "December"])}


def fetch_markdown():
    last = None
    for attempt in range(4):
        try:
            req = urllib.request.Request(JINA, headers={
                # jina's free tier is UA-sensitive: a full Chrome UA gets 403,
                # a plain descriptive UA passes. Keep the app's honest UA.
                "User-Agent": "mygov-dashboard/1.0 (+https://mygov.faizalmzain.com)",
            })
            with urllib.request.urlopen(req, timeout=60) as r:
                return r.read().decode("utf-8", "replace")
        except Exception as e:
            last = e
            sys.stderr.write(f"  attempt {attempt + 1}/4 failed: {e}\n")
            if attempt < 3:
                time.sleep(5 * (attempt + 1))   # 5s, 10s, 15s backoff
    raise RuntimeError(f"jina fetch failed after 4 attempts: {last}")


def parse_latest(md):
    """Return the newest alert {title, url, excerpt, ts} or None.

    The reader renders each alert as:
      ### [Title](https://myrapid.com.my/.../)
      Excerpt text…
      [Read More »](url)
      August 11, 2026  11:00 am
    Newest first - take the first block."""
    blocks = re.split(r"^### \[", md, flags=re.M)
    if len(blocks) < 2:
        return None
    head = blocks[1]
    tm = re.match(r"^([^\]]+)\]\((https?://[^)]+)\)", head)
    if not tm:
        return None
    rest = re.split(r"\[Read More", head, flags=re.I)[0]
    excerpt = re.sub(r"\s+", " ", rest.split("\n", 1)[1]).strip()[:240] \
        if "\n" in rest else re.sub(r"\s+", " ", rest).strip()[:240]
    dm = re.search(
        r"(" + MONTHS + r")\s+(\d{1,2}),\s+(\d{4})\s+(\d{1,2}):(\d{2})\s*(am|pm)",
        head, re.I)
    ts = None
    if dm:
        hh = int(dm.group(4))
        if "pm" in dm.group(6).lower() and hh < 12:
            hh += 12
        if "am" in dm.group(6).lower() and hh == 12:
            hh = 0
        # Posted times are MYT (UTC+8, no DST). MON is 0-based (mirrors the
        # worker's JS map) but datetime months are 1-based - +1 here. The
        # datetime is built in UTC (hour - 8), so epoch must come from
        # calendar.timegm - .timestamp() would reinterpret it as local time.
        import calendar
        import datetime as dt
        ts = calendar.timegm(dt.datetime(
            int(dm.group(3)), MON[dm.group(1).lower()] + 1, int(dm.group(2)),
            hh - 8, int(dm.group(5))).timetuple())
    return {
        "title": tm.group(1).strip(),
        "url": tm.group(2).strip(),
        "excerpt": excerpt,
        "ts": ts,
    }


def main():
    try:
        md = fetch_markdown()
    except Exception as e:
        sys.stderr.write(f"fetch failed: {e}\n")
        raise SystemExit(1)
    latest = parse_latest(md)
    out = {"updated": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
           "latest": latest}
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=1)
    print(f"wrote {OUT}: latest={'yes' if latest else 'NO'}"
          + (f" - {latest['title']}" if latest else ""))


if __name__ == "__main__":
    main()
