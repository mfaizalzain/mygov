#!/usr/bin/env python3
"""mygov SEO embedder + RSS feed generator.

Runs after any collector (radar / health / slow). Reads the three static
data bundles and:

1. Replaces the `<!-- SEO:SNAP -->` block inside public/index.html's
   <noscript> fallback with the CURRENT headline values (fuel prices,
   USD/MYR, CPI, population, top radar issues) so crawlers that never
   execute JS still see real, fresh numbers on first pass.
2. Writes public/feed.xml - an RSS 2.0 feed of today's top radar issues.

Idempotent: if index.html already carries the same snapshot it writes
nothing (so the collector's commit stays clean). Never crashes on missing
files - a missing bundle just yields fewer items.

Run:  python3 tools/embed_seo.py
"""
import datetime as dt
import html
import json
import os
import re
import sys
import xml.sax.saxutils as sax

INDEX = "public/index.html"
FEED = "public/feed.xml"
SITE = "https://mygov.faizalmzain.com"
MARK_START = "<!-- SEO:SNAP -->"
MARK_END = "<!-- /SEO:SNAP -->"


def load(path):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


def f2(x):
    return f"{x:.2f}" if isinstance(x, (int, float)) else "-"


def snapshot(radar, health, slow):
    """Build the <li> lines of the live snapshot (real current values)."""
    lines = []

    # ── fuel (weekly) ────────────────────────────────────────────────
    fuel = (slow or {}).get("fuel", {})
    fl = fuel.get("latest") or {}
    if fl:
        lines.append(
            f"<li><strong>Fuel</strong> - RON95 RM{f2(fl.get('ron95'))}, "
            f"RON97 RM{f2(fl.get('ron97'))}, diesel RM{f2(fl.get('diesel'))} "
            f"({html.escape(str(fl.get('date', '-')))}).</li>")

    # ── finance: latest business-day USD/MYR ─────────────────────────
    fxd = (slow or {}).get("finance", {}).get("fxd", []) if slow else []
    if fxd:
        # rows are [date, usd, sgd, eur, gbp, hkd-ish …]; USD is index 1
        date, usd = fxd[-1][0], fxd[-1][1]
        lines.append(
            f"<li><strong>Finance</strong> - USD/MYR {f2(usd)} "
            f"(business-day rate, {html.escape(str(date))}).</li>")

    # ── economy: headline CPI ────────────────────────────────────────
    cpi = None
    if slow:
        for s in slow.get("economy", {}).get("cpi", []):
            if s.get("name") == "headline":
                cpi = s
                break
    if cpi and cpi.get("pts"):
        d, v = cpi["pts"][-1]
        lines.append(f"<li><strong>Economy</strong> - CPI {v:.1f} points "
                     f"({html.escape(str(d))}).</li>")

    # ── population ───────────────────────────────────────────────────
    pop = (slow or {}).get("population", {}).get("latest") if slow else None
    if pop and isinstance(pop, (list, tuple)) and len(pop) >= 2:
        lines.append(f"<li><strong>Population</strong> - {pop[1]:,.1f} thousand ({pop[0]}).</li>")

    # ── health ───────────────────────────────────────────────────────
    if health and health.get("updated"):
        don = health.get("don", {})
        n = don.get("n")
        lines.append(
            f"<li><strong>Health</strong> - blood donations {n:,} units "
            f"({html.escape(str(health['updated']))}).</li>")

    # ── trend radar: top 3 ───────────────────────────────────────────
    issues = (radar or {}).get("top_issues", [])
    if issues:
        lines.append(
            "<li><strong>Trending now</strong> - "
            + " · ".join(html.escape(dash_clean(i.get("title_bm") or i.get("title_en") or ""))
                         for i in issues[:3])
            + ".</li>")

    return lines


def embed(radar, health, slow):
    try:
        src = open(INDEX, encoding="utf-8").read()
    except OSError as e:
        sys.stderr.write(f"[seo] cannot read {INDEX}: {e}\n")
        return False

    lines = snapshot(radar, health, slow)
    if not lines:
        return False  # nothing to write yet - keep the static fallback text

    body = "\n".join(lines)
    block = f"{MARK_START}\n{body}\n{MARK_END}"
    if MARK_START not in src:
        sys.stderr.write("[seo] no SEO:SNAP markers in index.html\n")
        return False

    new_src = re.sub(
        re.escape(MARK_START) + r".*?" + re.escape(MARK_END),
        lambda _: block, src, flags=re.S, count=1)
    if new_src == src:
        return False  # unchanged - nothing to commit
    with open(INDEX, "w", encoding="utf-8") as f:
        f.write(new_src)
    print(f"[seo] embedded {len(lines)} live values into {INDEX}")
    return True


def dash_clean(s):
    """Normalise en/em dashes to a plain hyphen (data titles carry U+2013)."""
    return (s or "").replace("\u2013", "-").replace("\u2014", "-")


def dash_clean_or(s, fallback="-"):
    """dash_clean, but returns fallback when the value is missing/blank."""
    return dash_clean(s) if s else fallback


def make_feed(radar):
    """RSS 2.0 feed of the top radar issues (or signals).

    Dates derive from radar.generated_at, not the wall clock, so the file
    only changes when the issue list actually changes - no commit churn on
    collectors that run twice a day with the same content."""
    issues = (radar or {}).get("top_issues", [])
    if not issues:
        return False
    try:
        gen = dt.datetime.fromisoformat((radar or {}).get("generated_at", ""))
    except (TypeError, ValueError):
        gen = dt.datetime.now(dt.timezone.utc)
    stamp = gen.strftime("%a, %d %b %Y %H:%M:%S +0000")
    items = []
    for i in issues:
        title = dash_clean(i.get("title_bm") or i.get("title_en") or "mygov issue")
        fc = i.get("fact_check") or {}
        desc = f"Category: {dash_clean_or(i.get('category'))} · Verdict: {dash_clean_or(fc.get('status'))}"
        link = SITE + "/#radar"
        items.append(f"""    <item>
      <title>{sax.escape(title)}</title>
      <link>{link}</link>
      <guid isPermaLink="false">mygov-radar-{i.get('rank', '?')}-{gen:%Y%m%d}</guid>
      <pubDate>{stamp}</pubDate>
      <description>{sax.escape(desc)}</description>
    </item>""")
    feed = f"""<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0" xmlns:atom="http://www.w3.org/2005/Atom">
  <channel>
    <title>mygov - Malaysia Trend Radar</title>
    <link>{SITE}</link>
    <description>Today's trending topics and fact-checked claims circulating in Malaysia, verified against real sources.</description>
    <language>ms-MY</language>
    <lastBuildDate>{stamp}</lastBuildDate>
    <atom:link href="{SITE}/feed.xml" rel="self" type="application/rss+xml"/>
{chr(10).join(items)}
  </channel>
</rss>
"""
    try:
        old = open(FEED, encoding="utf-8").read() if os.path.exists(FEED) else None
    except OSError:
        old = None
    if old == feed:
        return False  # unchanged - no commit churn
    try:
        with open(FEED, "w", encoding="utf-8") as f:
            f.write(feed)
        print(f"[seo] wrote {FEED} - {len(issues)} items")
        return True
    except OSError as e:
        sys.stderr.write(f"[seo] cannot write {FEED}: {e}\n")
        return False


def main():
    radar = load("public/radar.json")
    health = load("public/health.json")
    slow = load("public/slow.json")
    embed(radar, health, slow)
    make_feed(radar)


if __name__ == "__main__":
    main()
