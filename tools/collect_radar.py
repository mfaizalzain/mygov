#!/usr/bin/env python3
"""
mygov Trend Radar collector — Phase 1
Scoops Malaysia signals (Google Trends MY + news RSS + Sebenarnya.my fact-check RSS),
clusters into a ranked issue list, writes public/radar.json for the mygov dashboard.

Run:  python3 tools/collect_radar.py
Output: public/radar.json  (fetched by the dashboard's Trend Radar section)
"""
import json, re, html, sys, datetime, urllib.request, xml.etree.ElementTree as ET

OUT = "public/radar.json"
UA = {"User-Agent": "mygov-radar/0.1 (+https://mygov.faizalmzain.com)"}

NEWS_FEEDS = [
    ("malaymail", "https://www.malaymail.com/feed/rss", "en"),
    ("freemalaysiatoday", "https://www.freemalaysiatoday.com/category/nation/feed/", "en"),
    ("utusan", "https://www.utusan.com.my/feed/", "ms"),
    ("sebenarnya", "https://sebenarnya.my/feed/", "ms"),
]


def fetch(url, timeout=20):
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read().decode("utf-8", "ignore")


def parse_rss(text, source, lang, limit=30):
    items = []
    try:
        root = ET.fromstring(text)
        for it in root.iter("item"):
            title = html.unescape((it.findtext("title") or "").strip())
            link = (it.findtext("link") or "").strip()
            pub = (it.findtext("pubDate") or "").strip()
            if title and link:
                items.append({"source": source, "lang": lang, "title": title,
                              "url": link, "pub": pub})
            if len(items) >= limit:
                break
    except Exception as e:
        sys.stderr.write(f"  rss parse err {source}: {e}\n")
    return items


def get_trends(limit=25):
    """Google Trends geo=MY — rising queries (needs pytrends; skip gracefully)."""
    try:
        from pytrends.request import TrendReq
        pt = TrendReq(hl="en-US", tz=480)
        # realtime trending for MY (fall back to related queries if unavailable)
        try:
            df = pt.realtime_trending_searches(pn="malaysia")
            out = []
            for _, row in df.head(limit).iterrows():
                t = str(row.iloc[0])
                if t and t != "nan":
                    out.append({"query": t[:120], "source": "trends", "lang": "mixed"})
            if out:
                return out
        except Exception:
            pass
        # fallback: interest over time for a generic probe is not useful — return []
        return []
    except ImportError:
        return []


def main():
    print(f"[radar] {datetime.datetime.now():%Y-%m-%d %H:%M} collecting...")
    signals = []

    for source, url, lang in NEWS_FEEDS:
        try:
            text = fetch(url)
            items = parse_rss(text, source, lang)
            print(f"  {source}: {len(items)} items")
            signals.extend(items)
        except Exception as e:
            sys.stderr.write(f"  fetch err {source}: {e}\n")

    trends = get_trends()
    print(f"  trends: {len(trends)} entries")
    signals.extend(trends)

    now = datetime.datetime.now(datetime.timezone.utc).isoformat()
    payload = {
        "generated_at": now,
        "language": "bm-primary",
        "total_signals": len(signals),
        "signals": signals,
        "note": "Phase 1 collector — LLM clustering added when integrated with the agent loop.",
    }
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=1)
    print(f"[radar] wrote {OUT} ({len(signals)} signals, {len(json.dumps(payload))} bytes)")


if __name__ == "__main__":
    main()
