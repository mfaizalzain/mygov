#!/usr/bin/env python3
"""Travel Outlook collector for the mygov dashboard.

Turns the holiday + school calendar (already mirrored into slow.json from
the mycal API) into a forward-looking "Travel Outlook": the upcoming peak
travel periods of the next 8 weeks, each with a driver (school break,
public holiday, long weekend), an impact level, and bilingual one-liners
written by Gemini - plus a handful of general travel tips.

The same governing rule as collect_insights.py applies: **the calendar is
the ground truth, the LLM writes words**. Every date the model emits must
come from the facts it was handed (holidays + school breaks in the
window). Periods whose dates do not appear in the input are dropped, not
corrected - a model that invents a peak week is worse than none.

If Gemini is unavailable (no key, 429s exhausted, bad JSON), a
deterministic fallback is written instead: school breaks become "high"
periods and major holidays "extreme", all with dates straight from the
calendar and neutral bilingual text. The card always renders.

Run:  python3 tools/collect_travel.py
Deps: stdlib only. GOOGLE_API_KEY or GEMINI_API_KEY env var.
"""
import datetime as dt
import json
import os
import sys
import time
import urllib.error
import urllib.request

OUT = "public/travel.json"
WINDOW_DAYS = 56            # 8 weeks ahead
GEMINI = ("https://generativelanguage.googleapis.com/v1beta/models/"
          "gemini-flash-latest:generateContent")
IMPACT = ("extreme", "high", "moderate")

# The holidays that reliably move travel; everything else still counts but
# is rated moderate unless it forms a long weekend.
MAJOR = ("Chinese New Year", "Hari Raya", "Deepavali", "Wesak",
         "National Day", "Malaysia Day", "Christmas Day", "Labour Day",
         "Maulidur Rasul", "Prophet Muhammad")


def load(path):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        sys.stderr.write(f"  {path}: {e}\n")
        return {}


def gemini_key():
    return (os.environ.get("GOOGLE_API_KEY")
            or os.environ.get("GEMINI_API_KEY") or "").strip()


def gemini_call(key, body, tries=3):
    """POST to Gemini, retrying transient failures (same policy as the
    insights collector). Only aggregate public calendar data is sent."""
    last = None
    for attempt in range(tries):
        try:
            req = urllib.request.Request(
                GEMINI + "?key=" + key, data=body,
                headers={"Content-Type": "application/json"})
            with urllib.request.urlopen(req, timeout=90) as r:
                return json.loads(r.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            last = e
            if e.code != 429 and e.code < 500:
                raise
            sys.stderr.write(f"  gemini {e.code}, attempt {attempt + 1}/{tries}\n")
        except Exception as e:
            last = e
            sys.stderr.write(f"  gemini {type(e).__name__}, "
                             f"attempt {attempt + 1}/{tries}\n")
        if attempt < tries - 1:
            time.sleep(10 * (attempt + 1))
    raise last or RuntimeError("gemini failed")


def parse_json(text):
    """Tolerate markdown fences and stray prose around the JSON."""
    t = text.strip()
    if t.startswith("```"):
        t = t.split("```", 2)[1]
        if t.startswith("json"):
            t = t[4:]
    i, j = t.find("{"), t.rfind("}")
    if i >= 0 and j > i:
        t = t[i:j + 1]
    try:
        return json.loads(t)
    except Exception:
        return None


def build_facts(slow, start, end):
    """The exact calendar window handed to Gemini - every date it may use.

    Returns (holidays, breaks, long_weekends) as compact JSON-ready lists,
    all within [start, end]. Every date is clamped to >= start (today):
    a school break that began last week still matters, but Gemini must
    only ever see - and output - upcoming dates, never past ones.
    Breaks that ended before today are dropped entirely."""
    hol = []
    for h in (slow.get("holidays") or []):
        if not h or len(h) < 2:
            continue
        d, name = h[0], str(h[1])
        if d and start <= d <= end:
            major = bool(h[2]) if len(h) > 2 else False
            hol.append({"date": d, "name": name, "major": major})
    breaks = []
    for s in (slow.get("school") or []):
        if not s or not s.get("start") or not s.get("end"):
            continue
        if s["end"] < start or s["start"] > end:
            continue
        breaks.append({"start": max(s["start"], start), "end": s["end"],
                       "name": s.get("name", "School break")})
    return hol, breaks


def impact_of(holiday_names, in_break):
    """Deterministic impact rating used by the fallback AND as a sanity
    cross-check on the model's ratings."""
    if in_break and any(n in MAJOR for n in holiday_names):
        return "extreme"
    if in_break:
        return "high"
    if any(n in MAJOR for n in holiday_names):
        return "high"
    return "moderate"


def fallback(start, hol, breaks):
    """Deterministic outlook - every date from the calendar, no LLM.
    School breaks are 'high' peak periods; a major holiday inside a break
    escalates to 'extreme'. Holidays outside breaks become a 'moderate'
    period spanning the holiday date (or its long weekend)."""
    periods = []
    for b in breaks:
        in_names = [h["name"] for h in hol
                    if b["start"] <= h["date"] <= b["end"]]
        lvl = impact_of(in_names, True)
        periods.append({
            "start": b["start"], "end": b["end"],
            "driver": b["name"] + (f" + {' / '.join(in_names)}" if in_names else ""),
            "impact": lvl,
            "holidays": in_names,
            "t_en": (f"{b['name']} - school break. Expect busy highways and "
                     f"full hotels." if lvl != "extreme" else
                     f"{b['name']} and {in_names[0]} coincide - peak season, "
                     f"book early."),
            "t_ms": (f"{b['name']} - cuti sekolah. Jangkakan lebuh raya sesak "
                     f"dan hotel penuh." if lvl != "extreme" else
                     f"{b['name']} dan {in_names[0]} serentak - musim puncak, "
                     f"tempah awal."),
        })
    for h in hol:
        if any(h["date"] >= p["start"] and h["date"] <= p["end"]
               for p in periods):
            continue
        lvl = "high" if h["major"] else "moderate"
        periods.append({
            "start": h["date"], "end": h["date"],
            "driver": h["name"],
            "impact": lvl,
            "holidays": [h["name"]],
            "t_en": f"{h['name']} - public holiday." if lvl == "high" else
                    f"{h['name']} - a day off; light crowds expected.",
            "t_ms": f"{h['name']} - cuti umum." if lvl == "high" else
                    f"{h['name']} - cuti; orang ramai dijangka sederhana.",
        })
    periods.sort(key=lambda p: p["start"])
    tips = [
        {"t_en": "Travel early morning or late night to beat highway jams.",
         "t_ms": "Perjalanan awal pagi atau lewat malam untuk elak kesesakan lebuh raya."},
        {"t_en": "Book hotels and bus/plane tickets 3-4 weeks ahead during peak weeks.",
         "t_ms": "Tempah hotel dan tiket bas/pesawat 3-4 minggu awal semasa minggu puncak."},
        {"t_en": "Check the monsoon forecast before island trips on the east coast.",
         "t_ms": "Semak ramalan monsun sebelum ke pulau di pantai timur."},
    ]
    return {"periods": periods, "tips": tips}


PROMPT = """You write the "Travel Outlook" for a Malaysian public open-data dashboard.
Today is {date}. The window ahead is {window}.

These are the ONLY upcoming holidays and school breaks in that window. Every date you
output MUST come from this list - never invent or shift a date:

Holidays:
{holidays}

School breaks:
{breaks}

Return STRICT JSON only, no markdown fence:
{{"periods": [{{"start": "YYYY-MM-DD", "end": "YYYY-MM-DD", "driver": "what causes this peak (e.g. 'Term 2 school break + Merdeka long weekend')", "impact": "extreme|high|moderate", "t_en": "one English sentence on what travellers can expect", "t_ms": "the same sentence in natural Bahasa Melayu"}}], "tips": [{{"t_en": "...", "t_ms": "..."}}]}}

Rules:
- 1 to 4 periods, ordered by start date. Each period's start/end must be dates from the
  lists above (a period may span a break's range or a holiday date).
- impact: extreme = school break + major festival coincide; high = school break or
  major festival alone; moderate = other holidays / long weekends.
- 2 to 4 tips, bilingual, actionable (highways, booking, monsoon, rail).
- Bahasa Melayu must read naturally, not word-for-word translated.
- Factual and neutral. Do not invent statistics, prices or travel advisories."""


def build_outlook(slow, today):
    start = today.isoformat()
    end = (today + dt.timedelta(days=WINDOW_DAYS)).isoformat()
    hol, breaks = build_facts(slow, start, end)

    key = gemini_key()
    out = {"generated": start, "window": {"start": start, "end": end},
           "periods": [], "tips": [], "source": "fallback"}
    if not hol and not breaks:
        sys.stderr.write("  no holidays or school breaks in window - empty\n")
        return out

    if not key:
        sys.stderr.write("  no GOOGLE_API_KEY - writing deterministic fallback\n")
        out.update(fallback(start, hol, breaks))
        return out

    body = json.dumps({
        "contents": [{"parts": [{"text": PROMPT.format(
            date=start, window=f"{start} .. {end}",
            holidays=json.dumps(hol, ensure_ascii=False, indent=1),
            breaks=json.dumps(breaks, ensure_ascii=False, indent=1))}]}],
        # Headroom for thinking tokens, like collect_insights.py.
        "generationConfig": {"temperature": 0.3, "maxOutputTokens": 4096},
    }).encode("utf-8")
    try:
        payload = gemini_call(key, body)
        cand = (payload.get("candidates") or [{}])[0]
        parts = (cand.get("content") or {}).get("parts") or [{}]
        text = parts[0].get("text") or ""
        if not text.strip():
            reason = cand.get("finishReason", "unknown")
            sys.stderr.write(f"  gemini empty reply (finishReason={reason})\n")
            raise ValueError("empty")
    except Exception as e:
        sys.stderr.write(f"  gemini failed: {e} - fallback\n")
        out.update(fallback(start, hol, breaks))
        return out

    parsed = parse_json(text)
    if not parsed:
        sys.stderr.write("  gemini JSON unparseable - fallback\n")
        out.update(fallback(start, hol, breaks))
        return out

    # Ground every period: start/end must exist in the calendar facts.
    valid_dates = set()
    for h in hol:
        valid_dates.add(h["date"])
    for b in breaks:
        d = b["start"]
        while d <= b["end"]:
            valid_dates.add(d)
            d = (dt.date.fromisoformat(d) + dt.timedelta(days=1)).isoformat()
    periods = []
    for p in (parsed.get("periods") or [])[:4]:
        st, en = str(p.get("start", "")), str(p.get("end", ""))
        imp = str(p.get("impact", ""))
        if st not in valid_dates or en not in valid_dates:
            sys.stderr.write(f"  drop period {st}..{en}: date not in calendar\n")
            continue
        if imp not in IMPACT:
            sys.stderr.write(f"  drop period {st}..{en}: bad impact {imp}\n")
            continue
        en_t, ms_t = str(p.get("t_en", "")).strip(), str(p.get("t_ms", "")).strip()
        if not en_t or not ms_t:
            continue
        periods.append({"start": st, "end": en,
                        "driver": str(p.get("driver", "")).strip() or "Peak period",
                        "impact": imp, "t_en": en_t, "t_ms": ms_t})
    periods.sort(key=lambda p: p["start"])
    tips = []
    for t in (parsed.get("tips") or [])[:4]:
        en_t, ms_t = str(t.get("t_en", "")).strip(), str(t.get("t_ms", "")).strip()
        if en_t and ms_t:
            tips.append({"t_en": en_t, "t_ms": ms_t})

    if periods:
        out.update({"periods": periods, "tips": tips, "source": "gemini"})
    else:
        sys.stderr.write("  gemini produced no grounded periods - fallback\n")
        out.update(fallback(start, hol, breaks))
    return out


def main():
    slow = load("public/slow.json")
    today = dt.date.today()
    out = build_outlook(slow, today)
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, separators=(",", ":"))
    n = len(out.get("periods", []))
    sys.stderr.write(f"wrote {OUT}: {n} periods, {len(out.get('tips', []))} "
                     f"tips, source={out.get('source')}\n")


if __name__ == "__main__":
    main()
