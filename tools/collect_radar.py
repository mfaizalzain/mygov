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


def backfill_urls(issues, signals):
    """Attach real URLs to each issue's sources + fact_check by title matching.

    Gemini gets titles but often returns empty urls; we post-match against the
    collected signals (fuzzy, case-insensitive, first 40 chars) and fill in.
    Fact-check matching is done deterministically here (Gemini is unreliable
    at remembering sebenarnya titles between runs)."""
    def norm(t):
        t = (t or "").lower()
        t = t.replace("\xa0", " ")  # non-breaking space
        return re.sub(r"[^a-z0-9 ]", "", t)[:60].strip()

    def words(t):
        return set((t or "").lower().split())

    # index signals: normalized title prefix -> signal
    index = {}
    seben_signals = [s for s in signals if s["source"] == "sebenarnya"]
    for s in signals:
        k = norm(s["title"])
        if k and k not in index:
            index[k] = s

    def lookup(title):
        if not title:
            return None
        n = norm(title)
        if n in index:
            return index[n]
        for k, s in index.items():
            if k[:45] == n[:45]:
                return s
        return None

    def factcheck(issue_title, issue_title_en):
        """Deterministic: find a sebenarnya post sharing significant keywords."""
        stop = set("penjelasan berkenaan penggunaan kes dengan pada bagi yang dan untuk oleh seorang individu warga asing the a an of on in to for with about".split())
        iw = words(issue_title) | (words(issue_title_en) if issue_title_en else set())
        iw = {w for w in iw if len(w) > 4 and w not in stop}
        best, best_score = None, 0
        for s in seben_signals:
            sw = {w for w in words(s["title"]) if len(w) > 4 and w not in stop}
            overlap = len(iw & sw)
            if overlap > best_score:
                best, best_score = s, overlap
        if best and best_score >= 2:
            return {"status": "verified_claim", "sebenarnya_title": best["title"],
                    "sebenarnya_url": best["url"]}
        return {"status": "no_check_found", "sebenarnya_title": None,
                "sebenarnya_url": None}

    for issue in issues:
        for src in issue.get("sources", []):
            if not src.get("url"):
                m = lookup(src.get("title"))
                if m:
                    src["url"] = m["url"]
        # deterministic fact-check (overrides Gemini's unreliable memory)
        issue["fact_check"] = factcheck(issue.get("title_bm"), issue.get("title_en"))
    return issues


def factcheck_with_search(issue):
    """Grounded fact-check via Gemini + Google Search for ONE issue.

    Returns dict {status, verdict, reason, sources[]} — status one of
    verified_claim / debunked / no_check_found. Runs only for the top few
    issues (cost + latency). Never raises — falls back to no_check_found."""
    key = gemini_key()
    if not key:
        return {"status": "no_check_found", "verdict": None, "reason": None, "sources": []}
    title = issue.get("title_bm") or issue.get("title_en") or ""
    prompt = f"""A news trend is circulating in Malaysia: "{title}".
Treat it as a claim to verify. Use Google Search to check the latest
reports. Reply STRICT JSON only (no markdown):
{{"verdict": "TRUE|FALSE|PARTLY_TRUE|UNVERIFIED",
 "reason": "one sentence, in English",
 "sources": ["up to 3 short source names, e.g. AFP Fact Check, UNHCR"]}}
If it is a factual news event (not a claim), verdict TRUE with reason
"confirmed by multiple reports". If it is a false/fake claim, FALSE."""
    body = json.dumps({
        "contents": [{"parts": [{"text": prompt}]}],
        "tools": [{"google_search": {}}],
        "generationConfig": {"temperature": 0.1, "maxOutputTokens": 600},
    }).encode()
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_MODEL}:generateContent?key={key}"
    try:
        req = urllib.request.Request(url, data=body, headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=60) as r:
            d = json.load(r)
        text = d["candidates"][0]["content"]["parts"][0]["text"]
        text = re.sub(r"^```(json)?\s*|\s*```$", "", text.strip())
        parsed = json.loads(text)
        verdict = parsed.get("verdict", "UNVERIFIED")
        status = {"TRUE": "verified_claim", "PARTLY_TRUE": "verified_claim",
                  "FALSE": "debunked"}.get(verdict, "no_check_found")
        return {"status": status, "verdict": verdict,
                "reason": parsed.get("reason"), "sources": parsed.get("sources", [])}
    except Exception as e:
        sys.stderr.write(f"  factcheck err: {e}\n")
        return {"status": "no_check_found", "verdict": None, "reason": None, "sources": []}


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

    issues = backfill_urls(issues, signals)

    # Grounded fact-check (Gemini + Google Search) on top 5 — trends like
    # Rohingya are claim landscapes; verify with real sources.
    seben_fc = {i.get("rank"): i.get("fact_check", {}) for i in issues}
    checked = 0
    for i in issues[:5]:
        fc = factcheck_with_search(i)
        if fc.get("verdict"):
            checked += 1
            # keep the sebenarnya link if it exists (local match is authoritative)
            sb = seben_fc.get(i.get("rank"), {})
            if sb.get("status") != "no_check_found":
                fc["sebenarnya_title"] = sb.get("sebenarnya_title")
                fc["sebenarnya_url"] = sb.get("sebenarnya_url")
            i["fact_check"] = fc
    print(f"  grounded fact-check: {checked} issues verified")

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
