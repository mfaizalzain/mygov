#!/usr/bin/env python3
"""
mygov Trend Radar collector — Phase 1.5 (Gemini clustering & Grounded Fact-Checking)
Scoops Malaysia signals (news RSS + Sebenarnya.my fact-check RSS), clusters
into a ranked top-10 issue list via the Gemini API (gemini-flash-latest,
free tier), runs grounded fact-checks to extract detailed facts & claims,
and writes public/radar.json for the mygov dashboard.

Run:  python3 tools/collect_radar.py
Output: public/radar.json  (fetched by the dashboard's Trend Radar section)

Gemini key: read from GOOGLE_API_KEY in ~/.hermes/.env (or env).
Fallback: keyword-frequency clustering if the API call fails — never crash.
"""
import json, os, re, html, sys, time, datetime, email.utils, urllib.request, urllib.error
import xml.etree.ElementTree as ET
from collections import Counter

OUT = "public/radar.json"
HISTORY = "tools/radar_history.json"
HISTORY_DAYS = 7
UA = {"User-Agent": "mygov-radar/0.1 (+https://malaysia-at-a-glance.com)"}
GEMINI_MODEL = "gemini-flash-latest"

NEWS_FEEDS = [
    # /rss is Malay Mail's "All" feed — mostly world & lifestyle wire copy.
    # The /malaysia category feed is the local desk only.
    ("malaymail", "https://www.malaymail.com/feed/rss/malaysia", "en"),
    ("freemalaysiatoday", "https://www.freemalaysiatoday.com/category/nation/feed/", "en"),
    ("utusan", "https://www.utusan.com.my/feed/", "ms"),
    ("bernama_en", "https://www.bernama.com/en/rss/general.php", "en"),
    ("bernama_bm", "https://www.bernama.com/bm/rss/am.php", "ms"),
    ("astroawani", "https://www.astroawani.com/rss/berita-malaysia.xml", "ms"),
    ("sebenarnya", "https://sebenarnya.my/feed/", "ms"),
]

TRENDS_RSS = "https://trends.google.com/trending/rss?geo=MY"  # curl-able, no browser needed

SAFE_URL = re.compile(r"^https?://", re.I)

SOURCE_LABELS = {
    "malaymail": "Malay Mail",
    "freemalaysiatoday": "Free Malaysia Today",
    "utusan": "Utusan Malaysia",
    "bernama_en": "Bernama",
    "bernama_bm": "Bernama",
    "astroawani": "Astro Awani",
}


def _escape_json_string_controls(text):
    """Escape raw newlines/tabs inside JSON strings that Gemini sometimes emits."""
    out, in_str, escaped = [], False, False
    for ch in text:
        if in_str:
            if escaped:
                out.append(ch)
                escaped = False
            elif ch == "\\":
                out.append(ch)
                escaped = True
            elif ch == '"':
                out.append(ch)
                in_str = False
            elif ch == "\n":
                out.append("\\n")
            elif ch == "\r":
                out.append("\\r")
            elif ch == "\t":
                out.append("\\t")
            else:
                out.append(ch)
        else:
            if ch == '"':
                in_str = True
            out.append(ch)
    return "".join(out)


def parse_json_text(text):
    """Parse Gemini JSON that may be wrapped in fences or contain stray text."""
    text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text.strip())
    text = _escape_json_string_controls(text)
    text = re.sub(r",\s*([}\]])", r"\1", text)
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    start = text.find("{")
    if start == -1:
        raise ValueError("no JSON object found")
    depth = 0
    for idx in range(start, len(text)):
        if text[idx] == "{":
            depth += 1
        elif text[idx] == "}":
            depth -= 1
            if depth == 0:
                return json.loads(text[start:idx + 1])
    raise ValueError("no JSON object found")


def gemini_post(url, body, timeout=90, tries=3):
    """POST to Gemini, retrying transient failures."""
    last = None
    for attempt in range(tries):
        try:
            req = urllib.request.Request(
                url, data=body, headers={"Content-Type": "application/json"})
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return json.load(r)
        except urllib.error.HTTPError as e:
            last = e
            if e.code != 429 and e.code < 500:
                raise
            sys.stderr.write(f"  gemini {e.code}, attempt {attempt + 1}/{tries}\n")
        except Exception as e:
            last = e
            sys.stderr.write(f"  gemini {type(e).__name__}, attempt {attempt + 1}/{tries}\n")
        if attempt < tries - 1:
            time.sleep(10 * (attempt + 1))
    raise last or RuntimeError("gemini failed")


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
            desc = html.unescape((it.findtext("description") or "").strip())
            if title and SAFE_URL.match(link):
                items.append({"source": source, "lang": lang, "title": title,
                              "url": link, "pub": pub, "description": desc})
            if len(items) >= limit:
                break
    except Exception as e:
        sys.stderr.write(f"  rss parse err {source}: {e}\n")
    return items


def parse_trends_rss(text, limit=15):
    """Google Trends RSS: <item><title>query</title><ht:approx_traffic>.."""
    items = []
    try:
        root = ET.fromstring(text)
        for it in root.iter("item"):
            title = html.unescape((it.findtext("title") or "").strip())
            traffic = ""
            for el in it.iter():
                if el.tag.endswith("approx_traffic"):
                    traffic = (el.text or "").strip()
                    break
            if title:
                items.append({"source": "trends", "lang": "mixed", "title": title,
                              "url": "https://trends.google.com/trending?geo=MY",
                              "pub": "", "traffic": traffic})
            if len(items) >= limit:
                break
    except Exception as e:
        sys.stderr.write(f"  trends parse err: {e}\n")
    return items


def load_history():
    try:
        with open(HISTORY) as f:
            return json.load(f)
    except Exception:
        return []


def save_history(history):
    with open(HISTORY, "w", encoding="utf-8") as f:
        json.dump(history, f, ensure_ascii=False, indent=1)


def merge_history(signals):
    """Append today's signals to rolling history; prune entries older than HISTORY_DAYS."""
    today = str(datetime.date.today())
    history = load_history()
    cutoff = datetime.date.today() - datetime.timedelta(days=HISTORY_DAYS)
    history = [s for s in history if s.get("day", "") >= str(cutoff)]
    history.append({"day": today, "signals": signals})
    save_history(history)
    merged = []
    for entry in history:
        merged.extend(entry.get("signals", []))
    return merged


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
    """Ask gemini-flash-latest to cluster signals into top-10 issues requiring fact-checking."""
    key = gemini_key()
    if not key:
        return None
    compact = []
    for s in signals[:140]:
        compact.append(f"[{s['source']}] {s['title'][:110]}")
    prompt = f"""You cluster Malaysian news/trend/fact-check signals into the 10 hottest issues THAT REQUIRE FACT-CHECKING OR VERIFICATION.

Today: {datetime.date.today().isoformat()}. Signals (source|title):
{chr(10).join(compact)}

Return STRICT JSON only (no markdown fence), exactly this shape:
{{"top_issues": [
  {{"rank": 1, "title_bm": "short BM title", "title_en": "English title or null",
    "category": "politik|ekonomi|kesihatan|bencana|jenayah|pendidikan|agama|teknologi|antarabangsa|lain",
    "claim": "1 concise sentence describing the circulating claim or rumor",
    "fact_details": "2-3 detailed sentences explaining the verified facts, official statements, and true context",
    "source_count": 3,
    "sources": [{{"name": "malaymail", "title": "original headline", "url": ""}}],
    "fact_check": {{"status": "verified_claim|debunked|misleading|no_check_found",
      "verdict": "TRUE|FALSE|PARTLY_TRUE|UNVERIFIED",
      "claim": "circulating claim",
      "fact_details": "2-3 detailed sentences of verified facts",
      "sebenarnya_title": "matched sebenarnya post or null", "sebenarnya_url": null}}}}
]}}

Rules:
- FOCUS EXCLUSIVELY ON VIRAL CLAIMS, RUMORS, CONTROVERSIES, AND STATEMENTS THAT REQUIRE FACT-CHECKING.
- FILTER OUT standard breaking news, routine accidents, sports scores, daily road/weather updates, and routine political speeches.
- PERSISTENCE BEATS ONE-DAY SPIKES: topics appearing on MULTIPLE DAYS or across MULTIPLE sources rank higher.
- Dedupe across sources: same claim/issue = one issue; source_count = distinct sources.
- sebenarnya signals are official fact-check posts: if one addresses the issue, status=debunked (if false) or verified_claim (if true) or misleading.
- URLs: fill from the signal urls given (match by source+title); if unmatched, use "".
- Exactly 10 issues (fewer only if genuinely fewer distinct issues requiring verification)."""

    body = json.dumps({"contents": [{"parts": [{"text": prompt}]}],
                       "generationConfig": {"temperature": 0.2, "maxOutputTokens": 8192}}).encode()
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_MODEL}:generateContent?key={key}"
    d = gemini_post(url, body, timeout=90)
    text = d["candidates"][0]["content"]["parts"][0]["text"]
    parsed = parse_json_text(text)
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
             "category": "lain", "claim": None, "fact_details": None, "source_count": 0, "sources": [],
             "fact_check": {"status": "no_check_found", "verdict": "UNVERIFIED",
                            "claim": None, "fact_details": None,
                            "sebenarnya_title": None, "sebenarnya_url": None}} for i, w in enumerate(top)]


def backfill_urls(issues, signals):
    """Attach real URLs to each issue's sources + fact_check by title matching."""
    def norm(t):
        t = (t or "").lower()
        t = t.replace("\xa0", " ")
        return re.sub(r"[^a-z0-9 ]", "", t)[:60].strip()

    def words(t):
        return set((t or "").lower().split())

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
            return {"status": "verified_claim", "verdict": "FALSE", "sebenarnya_title": best["title"],
                    "sebenarnya_url": best["url"]}
        return {"status": "no_check_found", "verdict": "UNVERIFIED", "sebenarnya_title": None,
                "sebenarnya_url": None}

    for issue in issues:
        for src in issue.get("sources", []):
            if src.get("url") and not SAFE_URL.match(str(src["url"])):
                src["url"] = ""
        for src in issue.get("sources", []):
            if not src.get("url"):
                m = lookup(src.get("title"))
                if m:
                    src["url"] = m["url"]
        
        existing_fc = issue.get("fact_check") or {}
        sb = factcheck(issue.get("title_bm"), issue.get("title_en"))
        if sb.get("status") != "no_check_found":
            existing_fc["sebenarnya_title"] = sb.get("sebenarnya_title")
            existing_fc["sebenarnya_url"] = sb.get("sebenarnya_url")
            if existing_fc.get("status") in (None, "no_check_found"):
                existing_fc["status"] = "debunked"
                existing_fc["verdict"] = "FALSE"
        issue["fact_check"] = existing_fc

    return issues


def factcheck_with_search(issue):
    """Grounded fact-check via Gemini + Google Search for ONE issue to get detailed facts.

    Returns dict {status, verdict, claim, fact_details, reason, sources[]}."""
    key = gemini_key()
    if not key:
        return {"status": "no_check_found", "verdict": "UNVERIFIED", "claim": None, "fact_details": None, "reason": None, "sources": []}
    
    title = issue.get("title_bm") or issue.get("title_en") or ""
    prompt = f"""A viral claim, social media rumor, or issue is circulating in Malaysia: "{title}".

Treat it as a claim to verify. Use Google Search to check official statements and fact-checks (from SEBENARNYA.MY, MyCheck.My, Bernama, PDRM, MCMC, or Malaysian ministries).

Reply STRICT JSON only (no markdown):
{{
  "claim": "1 concise sentence stating the viral claim or rumor circulating",
  "verdict": "TRUE|FALSE|PARTLY_TRUE|UNVERIFIED",
  "fact_details": "2-3 comprehensive sentences explaining the verified facts, official statements, and true reality behind the claim",
  "reason": "1 short sentence summary of the verdict",
  "sources": ["up to 3 short official source names, e.g. SEBENARNYA.MY, PDRM, Malay Mail"]
}}

Rules:
- If claim is verified true: verdict = "TRUE"
- If claim is false/debunked/fake: verdict = "FALSE"
- If claim is misleading/partially true: verdict = "PARTLY_TRUE"
- If unverified: verdict = "UNVERIFIED"
"""
    body = json.dumps({
        "contents": [{"parts": [{"text": prompt}]}],
        "tools": [{"google_search": {}}],
        "generationConfig": {"temperature": 0.1, "maxOutputTokens": 800},
    }).encode()
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_MODEL}:generateContent?key={key}"
    try:
        d = gemini_post(url, body, timeout=60)
        text = d["candidates"][0]["content"]["parts"][0]["text"]
        parsed = parse_json_text(text)
        verdict = parsed.get("verdict", "UNVERIFIED")
        status = {
            "TRUE": "verified_claim",
            "PARTLY_TRUE": "misleading",
            "FALSE": "debunked"
        }.get(verdict, "no_check_found")
        return {
            "status": status,
            "verdict": verdict,
            "claim": parsed.get("claim") or issue.get("claim") or title,
            "fact_details": parsed.get("fact_details") or parsed.get("reason"),
            "reason": parsed.get("reason"),
            "sources": parsed.get("sources", [])
        }
    except Exception as e:
        sys.stderr.write(f"  factcheck err: {e}\n")
        return {"status": "no_check_found", "verdict": "UNVERIFIED", "claim": issue.get("claim") or title, "fact_details": issue.get("fact_details"), "reason": None, "sources": []}


def categorize_headline(title):
    t = (title or "").lower()
    if any(k in t for k in ["parlimen", "menteri", "pkr", "pas", "dap", "umno", "bersatu", "pn", "ph", "bn", "pilihan raya", "kerajaan", "anwar", "kabinet", "mp", "dewan rakyat", "election", "minister", "parliament"]):
        return "politik"
    if any(k in t for k in ["ringgit", "bursa", "saham", "inflasi", "ekonomi", "gdp", "cpi", "bank negara", "bnm", "harga", "subsidi", "cukai", "perdagangan", "eksport", "economy", "stock", "trade", "tax"]):
        return "ekonomi"
    if any(k in t for k in ["polis", "pdrm", "mahkamah", "tangkap", "dadah", "samun", "bunuh", "curi", "jenayah", "penjara", "siasat", "sprm", "dakwa", "ditahan", "police", "court", "arrest", "crime"]):
        return "jenayah"
    if any(k in t for k in ["banjir", "tanah runtuh", "ribut", "hujan lebat", "kebakaran", "kemalangan", "bencana", "flood", "landslide", "accident", "fire"]):
        return "bencana"
    if any(k in t for k in ["covid", "kesihatan", "hospital", "doktor", "kkm", "denggi", "penyakit", "health", "disease", "ministry of health"]):
        return "kesihatan"
    if any(k in t for k in ["harimau malaya", "badminton", "bola sepak", "sukan", "olimpiad", "liga", "sport", "football"]):
        return "sukan"
    return "nasional"


# Section paths every one of our sources uses for its foreign desk. A URL hit
# is unambiguous, so it drops the item outright.
FOREIGN_PATHS = (
    "/world/", "/dunia/", "/luar-negara/", "/luarnegara/", "/global/",
    "/international/", "/antarabangsa/", "/world-news/",
)

# Fallback for feeds that carry no section in the URL (Bernama's general wire).
# A foreign marker alone is not enough to drop a story — "Malaysians in Japan
# urged to stay alert" is local news — so an item only goes if it mentions a
# foreign place AND carries no Malaysian marker at all.
FOREIGN_HINTS = (
    "gaza", "israel", "palestin", "ukraine", "russia", "rusia", "china", "beijing",
    "india", "pakistan", "bangladesh", "myanmar", "thailand", "vietnam", "philippines",
    "filipina", "indonesia", "jakarta", "singapore", "singapura", "brunei", "japan",
    "jepun", "korea", "taiwan", "hong kong", "united states", "u.s.", "america",
    "washington", "trump", "britain", "uk ", "london", "france", "perancis", "germany",
    "jerman", "italy", "spain", "turkey", "turkiye", "iran", "iraq", "syria", "yemen",
    "saudi", "egypt", "mesir", "africa", "afrika", "kenya", "nigeria", "australia",
    "new zealand", "canada", "brazil", "mexico", "argentina", "afghanistan", "nepal",
    "sri lanka", "cambodia", "laos", "european union", "nato", "united nations",
)

MY_HINTS = (
    "malaysia", "malaysian", "msia", "kuala lumpur", " kl ", "putrajaya", "selangor",
    "johor", "penang", "pulau pinang", "perak", "kedah", "kelantan", "terengganu",
    "pahang", "negeri sembilan", "melaka", "malacca", "perlis", "sabah", "sarawak",
    "labuan", "ringgit", " rm", "pdrm", "kkm", "moh", "anwar", "agong", "sultan",
    "menteri", "kementerian", "dewan rakyat", "dewan negara", "parlimen", "parliament",
    "umno", "pkr", "dap", "pas", "bersatu", "barisan", "pakatan", "perikatan",
    "bursa", "bank negara", "bnm", "felda", "petronas", "mara", "jpj", "spm", "upsr",
    "rakyat", "negeri", "kampung", "bumiputera", "orang asli", "kementerian",
)


def is_malaysia_story(title, desc, url):
    """True when a headline is Malaysia-relevant. Foreign wire copy on our
    sources' shared feeds is the thing being filtered out here."""
    u = (url or "").lower()
    if any(p in u for p in FOREIGN_PATHS):
        return False
    blob = f" {(title or '').lower()} {(desc or '').lower()} "
    if any(m in blob for m in MY_HINTS):
        return True
    return not any(f in blob for f in FOREIGN_HINTS)


# A story older than this is not breaking. The band refreshes 3x a day, so a
# ~24h window still fills 20 slots between runs without going stale.
MAX_STORY_AGE_HOURS = 24

# Soft desks — real articles, but features and service copy, not breaking news.
SOFT_PATHS = (
    "/life/", "/lifestyle/", "/gaya-hidup/", "/eat-drink/", "/food/", "/resipi/",
    "/showbiz/", "/hiburan/", "/entertainment/", "/celebrity/", "/travel/",
    "/pelancongan/", "/opinion/", "/pendapat/", "/kolumnis/", "/columnist/",
    "/editorial/", "/rencana/", "/horoscope/", "/what-you-think/", "/review/",
)

SOFT_TITLE_HINTS = (
    "resipi", "horoskop", "tips ", "petua", "5 cara", "review:", "ulasan:",
    "here's how", "what to know", "things to do",
)


# ── how "breaking" a headline is ──────────────────────────────────────────
# Recency alone made a ministerial pleasantry outrank a fatal crash, because
# both were published in the last hour. These weights rank on consequence:
# what happened (incidents, deaths, arrests, disasters), how many newsrooms
# ran it, and how fresh it is — in that order.

# Something happened to someone, right now. The core of a breaking feed.
URGENT_WORDS = (
    "maut", "mati", "meninggal", "terbunuh", "bunuh", "korban", "mangsa", "cedera",
    "parah", "rentung", "kemalangan", "nahas", "terhempas", "karam", "tenggelam",
    "kebakaran", "terbakar", "letupan", "runtuh", "banjir", "tanah runtuh", "gempa",
    "ribut", "taufan", "darurat", "kecemasan", "amaran", "dipindahkan", "hilang",
    "diselamatkan", "ditahan", "tangkap", "cekup", "serbu", "rampas", "dakwa",
    "didakwa", "disyaki", "rasuah", "sprm", "letak jawatan", "dipecat", "digantung",
    "diharamkan", "tumpah", "wabak", "kes baharu", "ditutup", "tergendala",
    "dead", "died", "dies", "killed", "death", "fatal", "victim", "injured",
    "crash", "collision", "collapse", "fire", "blaze", "explosion", "blast",
    "flood", "landslide", "quake", "storm", "emergency", "evacuat", "missing",
    "rescue", "arrest", "detained", "raid", "seized", "charged", "graft",
    "corruption", "macc", "resign", "sacked", "suspended", "banned", "outbreak",
    "shut down", "halted", "grounded", "recall", "manhunt", "shooting", "stabb",
)

# Consequence without a body count: money, policy, prices, courts, elections.
IMPACT_WORDS = (
    "harga", "kenaikan", "naik harga", "turun harga", "subsidi", "cukai", "gst",
    "sst", "bantuan", "tarif", "gaji minimum", "kadar faedah", "opr", "belanjawan",
    "diluluskan", "dimansuhkan", "berkuat kuasa", "mahkamah", "hukuman", "penjara",
    "denda", "pilihan raya", "undi", "parlimen", "kabinet", "menteri", "titah",
    "dilancarkan", "diumumkan", "sekatan", "kuota", "price", "hike", "subsidy",
    "tax", "tariff", "wage", "rate cut", "budget", "approved", "abolished",
    "takes effect", "court", "sentenced", "jailed", "fined", "verdict", "ruling",
    "election", "parliament", "cabinet", "minister", "announce", "ban", "quota",
    "rm", "billion", "million", "juta", "bilion",
)

# Ceremony, congratulation and process copy. Real articles, not breaking news.
ROUTINE_WORDS = (
    "urges", "calls on", "hopes", "reminds", "congratulat", "welcomes", "praises",
    "thanks", "attends", "officiates", "launches book", "meets", "to discuss",
    "expected to", "may consider", "should remain", "must show", "says nothing",
    "no truth", "clarifies", "menyeru", "mengharap", "diharap", "mengucapkan",
    "tahniah", "merasmikan", "hadir", "berbincang", "bertemu", "dijangka",
    "perlu", "harus", "sedia", "komited", "yakin", "berpuas hati",
)


def significant_tokens(title):
    """Content words used to spot the same story running on several outlets."""
    words = re.findall(r"[a-z0-9']{4,}", (title or "").lower())
    return {w for w in words if w not in STOPWORDS}


STOPWORDS = {
    "yang", "untuk", "dengan", "dari", "dalam", "akan", "tidak", "kata", "kepada",
    "adalah", "pada", "ialah", "oleh", "juga", "lebih", "telah", "sudah", "boleh",
    "this", "that", "with", "from", "have", "will", "says", "said", "after",
    "over", "into", "amid", "than", "more", "been", "they", "their", "which",
    "about", "would", "could", "also", "what", "when", "were", "your",
}


def breaking_score(title, desc, age_hours, corroboration):
    """Higher = more worth leading the band with."""
    blob = f" {(title or '').lower()} {(desc or '').lower()} "
    score = 0.0
    score += 3.0 * sum(1 for w in URGENT_WORDS if w in blob)
    score += 1.0 * sum(1 for w in IMPACT_WORDS if w in blob)
    score -= 2.0 * sum(1 for w in ROUTINE_WORDS if w in blob)
    # Two newsrooms chasing the same story is the strongest signal we get that
    # it actually matters — no keyword list encodes editorial judgement.
    score += 2.5 * max(0, corroboration - 1)
    # Recency is a tie-breaker, not the ranking: a fatal crash from this
    # morning still outranks a press statement from ten minutes ago.
    if age_hours is not None:
        score += max(0.0, 3.0 - age_hours / 4.0)
    return score


def story_age_hours(pub):
    """Hours since publication, or None when the feed gave no usable date."""
    if not pub:
        return None
    try:
        t = email.utils.parsedate_to_datetime(pub)
    except Exception:
        return None
    if t is None:
        return None
    if t.tzinfo is None:
        t = t.replace(tzinfo=datetime.timezone.utc)
    delta = datetime.datetime.now(datetime.timezone.utc) - t
    # Small negative skew (a source clock running ahead) still counts as fresh.
    return max(delta.total_seconds() / 3600.0, 0.0)


def is_soft_news(title, url):
    u = (url or "").lower()
    if any(p in u for p in SOFT_PATHS):
        return True
    t = (title or "").lower()
    return any(h in t for h in SOFT_TITLE_HINTS)


def extract_breaking_news(signals, limit=20):
    """Build the breaking-news feed: recent, hard-news, Malaysia-only headlines,
    newest first. The raw feeds are just "latest N per source" — without the
    recency and soft-section filters below the band fills up with day-old
    lifestyle copy that is not breaking anything."""
    seen_titles = set()
    candidates = []

    def clean_text(s):
        s = html.unescape(s or "")
        s = re.sub(r"<[^>]+>", "", s)  # strip html tags
        s = re.sub(r"\s+", " ", s).strip()
        return s

    def title_key(t):
        return re.sub(r"[^a-z0-9]", "", (t or "").lower())[:40]

    news_signals = [s for s in signals if s.get("source") not in ("sebenarnya", "trends")]

    for s in news_signals:
        title = clean_text(s.get("title"))
        if not title or len(title) < 10:
            continue
        tk = title_key(title)
        if tk in seen_titles:
            continue
        seen_titles.add(tk)

        url = s.get("url", "")
        desc = clean_text(s.get("description") or "")
        if not is_malaysia_story(title, desc, url):
            continue
        if is_soft_news(title, url):
            continue

        age = story_age_hours(s.get("pub", ""))
        if age is None or age > MAX_STORY_AGE_HOURS:
            continue

        if len(desc) > 240:
            desc = desc[:237] + "…"
        src_key = s.get("source", "")
        candidates.append((age, desc, src_key, {
            "title_bm": title if s.get("lang") == "ms" else None,
            "title_en": title if s.get("lang") == "en" else None,
            "title": title,
            "source": src_key,
            "source_name": SOURCE_LABELS.get(src_key, src_key.replace("_", " ").title()),
            "url": url,
            "pub_date": s.get("pub", ""),
            "category": s.get("category") or categorize_headline(title),
            "summary": desc or title,
        }))

    # Group headlines that are the same story on different outlets: 3+ shared
    # content words. The group size is the corroboration signal, and only the
    # strongest member is published — the band used to run "Prosecutor says
    # police officer deliberately chased teen" directly above the same court
    # case from another paper.
    token_sets = [significant_tokens(c[3]["title"]) for c in candidates]
    group_of = list(range(len(candidates)))
    for i in range(len(candidates)):
        for j in range(i + 1, len(candidates)):
            if len(token_sets[i] & token_sets[j]) >= 3:
                merge_to = min(group_of[i], group_of[j])
                stale = max(group_of[i], group_of[j])
                group_of = [merge_to if g == stale else g for g in group_of]

    groups = {}
    for idx, gid in enumerate(group_of):
        groups.setdefault(gid, []).append(idx)

    scored = []
    for members in groups.values():
        sources = {candidates[i][2] for i in members}
        best, best_score = None, None
        for i in members:
            age, desc, _src, item = candidates[i]
            sc = breaking_score(item["title"], desc, age, len(sources))
            if best_score is None or sc > best_score:
                best, best_score = (age, item), sc
        age, item = best
        item["reported_by"] = len(sources)
        scored.append((best_score, -age, item))

    scored.sort(key=lambda x: (-x[0], -x[1]))  # consequence first, then freshness
    breaking = []
    for score, _, item in scored[:limit]:
        item["rank"] = len(breaking) + 1
        item["breaking_score"] = round(score, 2)
        breaking.append(item)
    return breaking


def fetch_signals():
    """Pull every news + trends feed once. Shared by the full and news-only runs."""
    signals = []
    for source, url, lang in NEWS_FEEDS:
        try:
            items = parse_rss(fetch(url), source, lang)
            print(f"  {source}: {len(items)} items")
            signals.extend(items)
        except Exception as e:
            sys.stderr.write(f"  fetch err {source}: {e}\n")

    try:
        trends = parse_trends_rss(fetch(TRENDS_RSS))
        print(f"  trends: {len(trends)} items")
        signals.extend(trends)
    except Exception as e:
        sys.stderr.write(f"  trends err: {e}\n")
    return signals


def refresh_news_only():
    """Cheap intraday pass: refresh only breaking_news inside the existing
    radar.json. No Gemini calls, no history merge — the clustered top_issues
    and their fact-checks are left exactly as the daily full run wrote them."""
    print(f"[radar] {datetime.datetime.now():%Y-%m-%d %H:%M} news-only refresh...")
    try:
        with open(OUT, encoding="utf-8") as f:
            payload = json.load(f)
    except Exception as e:
        sys.stderr.write(f"[radar] no existing {OUT} ({e}) — falling back to a full run\n")
        return main()

    signals = fetch_signals()
    breaking = extract_breaking_news(signals, limit=20)
    if not breaking:
        sys.stderr.write("[radar] no breaking stories parsed — keeping previous feed\n")
        return

    payload["breaking_news"] = breaking
    payload["news_updated_at"] = datetime.datetime.now(datetime.timezone.utc).isoformat()
    payload["total_signals"] = len(signals)
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=1)
    print(f"[radar] wrote {OUT} — {len(breaking)} breaking stories from {len(signals)} signals (issues untouched)")


def main():
    print(f"[radar] {datetime.datetime.now():%Y-%m-%d %H:%M} collecting...")
    signals = fetch_signals()

    merged = merge_history(signals)
    print(f"  history window: {len(merged)} signals (7-day rolling)")

    issues = None
    try:
        issues = cluster_with_gemini(merged)
    except Exception as e:
        sys.stderr.write(f"  gemini err: {e}\n")
    if issues:
        print(f"  gemini: {len(issues)} issues")
    else:
        issues = cluster_keyword(merged)
        print(f"  fallback keyword clustering: {len(issues)} issues")

    issues = backfill_urls(issues, signals)

    # Grounded fact-check (Gemini + Google Search) on top 8 issues — extract rich claims & fact_details
    seben_fc = {i.get("rank"): i.get("fact_check", {}) for i in issues}
    checked = 0
    for i in issues[:8]:
        fc = factcheck_with_search(i)
        if fc.get("verdict"):
            checked += 1
            sb = seben_fc.get(i.get("rank"), {})
            if sb.get("status") != "no_check_found":
                fc["sebenarnya_title"] = sb.get("sebenarnya_title")
                fc["sebenarnya_url"] = sb.get("sebenarnya_url")
                if fc.get("status") in (None, "no_check_found"):
                    fc["status"] = sb.get("status")
                    fc["verdict"] = sb.get("verdict") or fc.get("verdict")
            
            # Attach root-level claim and fact_details for easy rendering
            i["claim"] = fc.get("claim")
            i["fact_details"] = fc.get("fact_details")
            i["fact_check"] = fc

    print(f"  grounded fact-check: {checked} issues verified with rich fact details")

    breaking = extract_breaking_news(signals, limit=20)
    print(f"  extracted breaking news: {len(breaking)} stories")

    now_iso = datetime.datetime.now(datetime.timezone.utc).isoformat()
    payload = {
        "generated_at": now_iso,
        "news_updated_at": now_iso,
        "language": "bm-primary",
        "top_issues": issues,
        "breaking_news": breaking,
        "total_signals": len(signals),
        "history_window_signals": len(merged),
        "history_days": HISTORY_DAYS,
    }
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=1)
    print(f"[radar] wrote {OUT} — {len(issues)} issues & {len(breaking)} breaking stories from {len(signals)} signals ({len(merged)} in 7-day window)")


if __name__ == "__main__":
    if "--news-only" in sys.argv:
        refresh_news_only()
    else:
        main()
