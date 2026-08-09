#!/usr/bin/env python3
"""
mygov Trend Radar collector — Phase 1.5 (Gemini clustering)
Scoops Malaysia signals (news RSS + Sebenarnya.my fact-check RSS), clusters
into a ranked top-10 issue list via the Gemini API (gemini-flash-latest,
free tier), writes public/radar.json for the mygov dashboard.

Run:  python3 tools/collect_radar.py
Output: public/radar.json  (fetched by the dashboard's Trend Radar section)

Gemini key: read from GOOGLE_API_KEY in ~/.hermes/.env (or env).
Fallback: keyword-frequency clustering if the API call fails — never crash.
"""
import json, os, re, html, sys, datetime, urllib.request, xml.etree.ElementTree as ET
from collections import Counter

OUT = "public/radar.json"
UA = {"User-Agent": "mygov-radar/0.1 (+https://mygov.faizalmzain.com)"}
GEMINI_MODEL = "gemini-flash-latest"

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


def gemini_key():
    k = os.environ.get("GOOGLE_API_KEY")
    if k:
        return k
    try:
        for line in open(os.path.expanduser("~/.hermes/.env")):
            if line.startswith("GOOGLE_API_KEY="):
                return line.strip().split("=", 1)[1]
    except Exception:
        pass
    return None


def cluster_with_gemini(signals):
    """Ask gemini-flash-latest to cluster signals into top-10 issues. Returns list or None."""
    key = gemini_key()
    if not key:
        return None
    # compact signal list: source|title (cap ~140 signals to fit context)
    compact = []
    for s in signals[:140]:
        compact.append(f"[{s['source']}] {s['title'][:110]}")
    prompt = f"""You cluster Malaysian news/fact-check signals into the 10 hottest current issues.

Today: {datetime.date.today().isoformat()}. Signals (source|title):
{chr(10).join(compact)}

Return STRICT JSON only (no markdown fence), exactly this shape:
{{"top_issues": [
  {{"rank": 1, "title_bm": "short BM title", "title_en": "English title or null",
    "category": "politik|ekonomi|kesihatan|bencana|jenayah|pendidikan|agama|teknologi|antarabangsa|lain",
    "source_count": 3,
    "sources": [{{"name": "malaymail", "title": "original headline", "url": ""}}],
    "fact_check": {{"status": "verified_claim|debunked|no_check_found",
      "sebenarnya_title": "matched sebenarnya post or null", "sebenarnya_url": null}}}}
]}}
Rules:
- Dedupe across sources: same story = one issue; source_count = distinct sources.
- Cross-source frequency + recency drive ranking. Nationwide > niche.
- sebenarnya signals are fact-check posts: if one addresses the issue,
  status=debunked (claim is false) or verified_claim; else no_check_found.
- URLs: fill from the signal urls you were given (match by source+title); if
  you cannot match, use "" for url.
- Exactly 10 issues (fewer only if genuinely fewer distinct issues)."""
    body = json.dumps({"contents": [{"parts": [{"text": prompt}]}],
                       "generationConfig": {"temperature": 0.2, "maxOutputTokens": 8192}}).encode()
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_MODEL}:generateContent?key={key}"
    req = urllib.request.Request(url, data=body, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=90) as r:
        d = json.load(r)
    text = d["candidates"][0]["content"]["parts"][0]["text"]
    # strip markdown fences if present
    text = re.sub(r"^```(json)?\s*|\s*```$", "", text.strip())
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        # rescue: find the largest balanced {...} block
        start = text.find("{")
        depth = 0
        for idx in range(start, len(text)):
            if text[idx] == "{":
                depth += 1
            elif text[idx] == "}":
                depth -= 1
                if depth == 0:
                    parsed = json.loads(text[start:idx + 1])
                    break
        else:
            raise
    return parsed.get("top_issues")


def cluster_keyword(signals):
    """Fallback: crude keyword clustering (no LLM). Never used if Gemini works."""
    stop = set("malaysia the a an to of on in for and with says after as new over from by per at is are be has have will its his her".split())
    words = Counter()
    for s in signals:
        for w in re.findall(r"[A-Za-z]{4,}", s["title"].lower()):
            if w not in stop:
                words[w] += 1
    top = [w for w, _ in words.most_common(12)]
    return [{"rank": i + 1, "title_bm": w.title(), "title_en": None,
             "category": "lain", "source_count": 0, "sources": [],
             "fact_check": {"status": "no_check_found", "sebenarnya_title": None,
                            "sebenarnya_url": None}} for i, w in enumerate(top)]


def main():
    print(f"[radar] {datetime.datetime.now():%Y-%m-%d %H:%M} collecting...")
    signals = []
    for source, url, lang in NEWS_FEEDS:
        try:
            items = parse_rss(fetch(url), source, lang)
            print(f"  {source}: {len(items)} items")
            signals.extend(items)
        except Exception as e:
            sys.stderr.write(f"  fetch err {source}: {e}\n")

    issues = None
    try:
        issues = cluster_with_gemini(signals)
    except Exception as e:
        sys.stderr.write(f"  gemini err: {e}\n")
    if issues:
        print(f"  gemini: {len(issues)} issues")
    else:
        issues = cluster_keyword(signals)
        print(f"  fallback keyword clustering: {len(issues)} issues")

    payload = {
        "generated_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "language": "bm-primary",
        "top_issues": issues,
        "total_signals": len(signals),
    }
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=1)
    print(f"[radar] wrote {OUT} — {len(issues)} issues from {len(signals)} signals")


if __name__ == "__main__":
    main()
