#!/usr/bin/env python3
"""Daily insights + forecasts collector for the mygov dashboard.

Writes two files, both generated entirely in CI so a visitor never pays for an
AI call and the page still works offline:

  public/forecasts.json  statistically computed, with prediction intervals
  public/insights.json   a bilingual "Today in Malaysia" briefing, written by
                         Gemini but carrying only numbers the statistics
                         produced

The governing rule is **statistics for numbers, LLM for words**, and it is
enforced in code by ground() rather than requested in the prompt.

What is forecast, and what deliberately is not
----------------------------------------------
Measured on this repo's own data (see docs/ai-insights-forecasts-plan.md):

  forecast     ridership per service, blood donations per type - human-routine
               count series where knowing last week's same weekday beats
               knowing yesterday by 13-55%
  not forecast fuel (RON95 is an administered price: 26 distinct values in 104
               weeks, spanning a subsidy peg at 2.05 and a float at 4.27 - a
               policy break, not a process), FX (a drift model scores a WORSE
               one-step MAE than "tomorrow = today": 0.01022 vs 0.00991, the
               textbook random walk), CPI and controlled grocery items

Nothing here forecasts a price set by government. If that is ever requested,
re-run backtest_gain() first: the measurement decides, not the request.

Run:  python3 tools/collect_insights.py [--forecasts-only|--brief-only]
Deps: stdlib only. (Deliberately no statsforecast - numba+scipy+llvmlite is a
      slow, fragile CI install for gains no backtest has demonstrated here.)
"""
import argparse
import datetime as dt
import json
import os
import re
import statistics as st
import sys
import urllib.error
import urllib.request

OUT_FC = "public/forecasts.json"
OUT_IN = "public/insights.json"

HORIZON = 14        # two full weekly cycles
SEASON = 7
MIN_GAIN = 0.05     # a forecast must beat naive by 5% to be worth publishing
BASELINE_DAYS = 365  # trailing window the anomaly baseline is measured over
EPOCH = dt.date(1970, 1, 1)

GEMINI = ("https://generativelanguage.googleapis.com/v1beta/models/"
          "gemini-flash-latest:generateContent")


def iso_of(day):
    """Day number (days since epoch, the dense-series unit) -> YYYY-MM-DD."""
    return (EPOCH + dt.timedelta(days=int(day))).isoformat()


def load(path):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        sys.stderr.write(f"  {path}: {e}\n")
        return {}


# ════════════════════════════ forecasting ════════════════════════════
"""Lags below are counted in DAYS, over the dense array with its gaps left in.

Compacting the Nones out first and taking hist[-7] would mean "7 observations
ago", which is only "7 days ago" for a series with no gaps. Rapid rail komuter
has 1,060 gaps in 2,126 days and shuttle_tebrau 612, so compaction silently
destroys the very weekly cycle these functions exist to exploit."""


def _lag_pairs(vals, lag):
    """(earlier, later) value pairs exactly `lag` days apart, gaps skipped."""
    out = []
    for i in range(len(vals) - lag):
        a, b = vals[i], vals[i + lag]
        if a is not None and b is not None:
            out.append((a, b))
    return out


def backtest_gain(vals, season=SEASON):
    """Fractional MAE improvement of seasonal-naive over naive, in-sample.

    <= 0 means the weekly lag carries no information for this series and no
    forecast should be published for it. This is the gate that keeps
    unforecastable series out: on the live data it passes shuttle_tebrau and
    the blood series while rejecting ets and intercity."""
    if len([v for v in vals if v is not None]) < season * 8:
        return 0.0
    naive = [abs(b - a) for a, b in _lag_pairs(vals, 1)]
    snaive = [abs(b - a) for a, b in _lag_pairs(vals, season)]
    if not naive or not snaive:
        return 0.0
    mn = sum(naive) / len(naive)
    ms = sum(snaive) / len(snaive)
    return 0.0 if mn == 0 else (mn - ms) / mn


def forecast_series(vals, horizon=HORIZON, season=SEASON):
    """Seasonal-naive point forecast with empirical prediction intervals.

    Forecast day n+i takes the observation from day n+i-season, falling back
    through earlier cycles when that day is itself a gap. The band is the
    empirical 10th/90th percentile of the same estimator's own residuals over
    a trailing window, so it reports the accuracy the method actually achieved
    on this series rather than assuming a distribution. Returns [] when the
    series is too short or too sparse to justify one."""
    if len([v for v in vals if v is not None]) < season * 8:
        return []
    diffs = sorted(b - a for a, b in _lag_pairs(vals, season)[-BASELINE_DAYS:])
    if not diffs:
        return []
    lo_q = diffs[int(0.10 * len(diffs))]
    hi_q = diffs[int(0.90 * len(diffs))]
    n = len(vals)
    out = []
    for i in range(horizon):
        # Walk back in whole cycles until a real observation is found, so a
        # gap on the same weekday does not blank a forecast day.
        base, j = None, n + i - season
        while j >= 0 and base is None:
            base = vals[j] if j < n else out[j - n]["mid"]
            if base is None:
                j -= season
        if base is None:
            return []
        out.append({"mid": round(base, 2),
                    "lo": round(base + lo_q, 2),
                    "hi": round(base + hi_q, 2)})
    return out


def dense_vals(block):
    """Dense-daily block -> (t0, [values]) with trailing Nones trimmed."""
    if not block or not block.get("keys"):
        return None
    return block


def deholiday(vals, t0, holidays):
    """Replace major-holiday values with a local median before fitting.

    Chinese New Year moves Komuter ridership by ~2x. Left in, it is read as a
    20-sigma anomaly every year AND it becomes the base the following week is
    forecast from. Neither is acceptable, so holidays are neutralised for
    fitting; the UI still marks them from slow.json's holiday table."""
    if not holidays:
        return list(vals)
    out = list(vals)
    for i, v in enumerate(out):
        if v is None or iso_of(t0 + i) not in holidays:
            continue
        lo, hi = max(0, i - 10), min(len(out), i + 11)
        near = [out[j] for j in range(lo, hi)
                if out[j] is not None and iso_of(t0 + j) not in holidays]
        if near:
            out[i] = st.median(near)
    return out


def build_forecasts(slow, health, holidays):
    """Forecast every daily count series that beats naive by MIN_GAIN."""
    fc = {"generated": dt.date.today().isoformat(),
          "horizon": HORIZON, "ridership": {}, "blood": {}}
    sources = [("ridership", (slow.get("mobility") or {}).get("rid")),
               ("blood", (health or {}).get("don"))]
    for bucket, src in sources:
        src = dense_vals(src)
        if not src:
            continue
        for key in src["keys"]:
            raw = src["series"].get(key) or []
            clean = deholiday(raw, src["t0"], holidays)
            gain = backtest_gain(clean)
            if gain <= MIN_GAIN:
                sys.stderr.write(f"  skip {bucket}/{key}: gain {gain:+.1%}\n")
                continue
            f = forecast_series(clean)
            if not f:
                continue
            # t0/n locate the forecast against the series the client already
            # loaded. History is deliberately NOT copied in - two copies of the
            # same numbers can disagree.
            fc[bucket][key] = {"gain": round(gain, 3), "t0": src["t0"],
                               "n": src["n"], "fc": f}
            sys.stderr.write(f"  {bucket}/{key}: gain {gain:+.1%}, "
                             f"{len(f)}d forecast\n")
    return fc


# ════════════════════════════ anomaly detection ═══════════════════════
def anomalies(series_map, holidays, z=2.5):
    """Residual outliers against the weekly seasonal norm.

    Detection runs before any LLM sees the data: statistics decide what is
    interesting, the model only phrases it. Holidays are excluded because they
    are explained, not anomalous."""
    hits = []
    for key, meta in series_map.items():
        vals, t0 = meta["vals"], meta["t0"]
        pairs = [(i, vals[i]) for i in range(len(vals)) if vals[i] is not None]
        if len(pairs) < SEASON * 8:
            continue
        idx = {i: v for i, v in pairs}
        resid = []
        for i, v in pairs:
            prev = idx.get(i - SEASON)
            if prev is not None:
                resid.append((i, v, v - prev))
        if len(resid) < 30:
            continue
        # Baseline from a trailing window, not the whole history: these series
        # span COVID-era swings and regime shifts whose variance is not today's
        # variance. Whole-history sigma for Komuter is 7,353 against 4,849 for
        # the last 180 days - wide enough to hide anything a reader would
        # actually notice.
        deltas = [r[2] for r in resid[-BASELINE_DAYS:]]
        sd = st.pstdev(deltas) or 1.0
        mean = st.fmean(deltas)
        for i, v, d in resid[-30:]:                 # only the recent window
            day = iso_of(t0 + i)
            if day in holidays:
                continue
            score = (d - mean) / sd
            if abs(score) >= z:
                hits.append({"key": key, "date": day, "value": round(v, 2),
                             "expected": round(v - d, 2), "z": round(score, 2),
                             "dir": "up" if d > 0 else "down"})
    hits.sort(key=lambda h: -abs(h["z"]))
    return hits


# ════════════════════════════ grounding gate ══════════════════════════
def _numbers_in(obj, acc):
    if isinstance(obj, bool):
        return
    if isinstance(obj, (int, float)):
        acc.update({f"{obj}", f"{obj:.0f}", f"{obj:.1f}", f"{obj:.2f}",
                    f"{round(obj)}"})
        if obj:
            acc.add(f"{abs(obj):.1f}")
            acc.add(f"{abs(obj):.2f}")
    elif isinstance(obj, dict):
        for v in obj.values():
            _numbers_in(v, acc)
    elif isinstance(obj, (list, tuple)):
        for v in obj:
            _numbers_in(v, acc)


def ground(text, facts):
    """True if every numeral in `text` appears in `facts`.

    A prompt instruction saying "do not invent data" is a hope, not a control.
    This is the control. Without it we eventually publish a hallucinated figure
    under a .gov.my attribution, which is not a recoverable error for a project
    whose whole value is being trustworthy about official numbers."""
    allowed = set()
    _numbers_in(facts, allowed)
    # Strip currency prefixes so "RM3.77" reads as the quantity 3.77, then
    # ignore digit runs glued to letters - "RON95", "B40" and "PeKa B40" are
    # product names, not claims about the world. The quantity in
    # "RON95 rose to RM4.20" is 4.20, and that is what must be grounded.
    clean = re.sub(r"\b(?:RM|MYR|USD|SGD|EUR|GBP|JPY|THB|AUD|CNY|IDR)\s*",
                   " ", str(text), flags=re.I)
    for tok in re.findall(r"(?<![A-Za-z0-9.])\d+(?:[.,]\d+)*", clean):
        plain = tok.replace(",", "")
        if plain in allowed:
            continue
        # tolerate a trailing zero difference ("3.70" vs "3.7")
        try:
            if f"{float(plain):.2f}" in allowed or f"{float(plain):.1f}" in allowed:
                continue
        except ValueError:
            pass
        return False
    return True


# ════════════════════════════ the brief ═══════════════════════════════
def gemini_key():
    return (os.environ.get("GOOGLE_API_KEY")
            or os.environ.get("GEMINI_API_KEY") or "").strip()


def build_facts(slow, health, prices, radar, fc, hits):
    """The single source of truth for every number the brief may use."""
    f = {}
    fuel = (slow.get("fuel") or {}).get("latest") or {}
    prev = (slow.get("fuel") or {}).get("prev") or {}
    if fuel:
        f["ron95"] = fuel.get("ron95")
        f["ron97"] = fuel.get("ron97")
        f["diesel"] = fuel.get("diesel")
    if fuel and prev and fuel.get("ron95") and prev.get("ron95"):
        f["ron95_change"] = round(fuel["ron95"] - prev["ron95"], 2)
    fxd = (slow.get("finance") or {}).get("fxd") or []
    if fxd:
        f["usd"] = fxd[-1][1]
    basket = (prices.get("basket") or {})
    if basket.get("national"):
        f["basket"] = basket["national"][-1]
        f["basket_n"] = basket.get("n")
    f["anomalies"] = hits[:6]
    f["forecast_days"] = fc.get("horizon")
    for bucket in ("ridership", "blood"):
        for k, v in (fc.get(bucket) or {}).items():
            f[f"fc_{bucket}_{k}"] = v["fc"][0]["mid"]
    f["radar"] = [i.get("title") for i in (radar.get("issues") or [])[:3]]
    return f


PROMPT = """You write the daily "Today in Malaysia" briefing for a public open-data dashboard.
Today is {date}.

These are the ONLY facts you may use. Every number you write must appear here verbatim:
{facts}

Statistically detected anomalies (already filtered for public holidays - these are
the movements a reader could not have predicted):
{hits}

Return STRICT JSON only, no markdown fence:
{{"bullets": [{{"cat": "prices|finance|economy|health|mobility|trends",
  "t_en": "one sentence in English", "t_ms": "the same fact in natural Bahasa Melayu",
  "sec": "fuel|finance|economy|health|mobility|radar"}}]}}

Rules:
- 4 to 5 bullets maximum, one fact per bullet.
- Use ONLY numbers from the facts above. Never compute, round differently, or invent a number.
- Prefer the anomalies: a reader can already see today's headline values on the page.
- Factual and neutral. State what happened. Do not speculate, advise, or editorialise.
- Bahasa Melayu must read naturally, not word-for-word translated.
"""


def build_brief(slow, health, prices, radar, fc, hits):
    facts = build_facts(slow, health, prices, radar, fc, hits)
    key = gemini_key()
    out = {"generated": dt.date.today().isoformat(), "bullets": []}
    if not key:
        sys.stderr.write("  no GOOGLE_API_KEY - writing empty brief\n")
        out["error"] = "no key"
        return out

    body = json.dumps({
        "contents": [{"parts": [{"text": PROMPT.format(
            date=out["generated"],
            facts=json.dumps(facts, ensure_ascii=False, indent=1),
            hits=json.dumps(hits[:6], ensure_ascii=False, indent=1))}]}],
        "generationConfig": {"temperature": 0.2, "maxOutputTokens": 1400},
    }).encode("utf-8")
    try:
        req = urllib.request.Request(
            GEMINI + "?key=" + key, data=body,
            headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=90) as r:
            payload = json.loads(r.read().decode("utf-8"))
        text = payload["candidates"][0]["content"]["parts"][0]["text"]
    except Exception as e:
        sys.stderr.write(f"  gemini failed: {e}\n")
        out["error"] = "gemini"
        return out

    parsed = parse_json(text)
    raw = (parsed or {}).get("bullets") or []
    kept, dropped = [], 0
    for b in raw:
        en, ms = str(b.get("t_en", "")).strip(), str(b.get("t_ms", "")).strip()
        if not en or not ms:
            continue
        # Both languages must pass; a number invented in only one is still a
        # number we published.
        if not (ground(en, facts) and ground(ms, facts)):
            dropped += 1
            sys.stderr.write(f"  DROPPED (ungrounded): {en[:70]}\n")
            continue
        kept.append({"cat": str(b.get("cat", "")), "sec": str(b.get("sec", "")),
                     "t_en": en, "t_ms": ms})
    out["bullets"] = kept[:5]
    sys.stderr.write(f"  brief: {len(out['bullets'])} bullets kept, "
                     f"{dropped} dropped by grounding gate\n")
    return out


def parse_json(text):
    """Strict-JSON rescue: strip fences, then balance braces. Mirrors the
    proven parser in collect_radar.py."""
    t = str(text).strip()
    t = re.sub(r"^```(?:json)?|```$", "", t, flags=re.M).strip()
    try:
        return json.loads(t)
    except Exception:
        pass
    i, depth = t.find("{"), 0
    if i < 0:
        return None
    for j in range(i, len(t)):
        if t[j] == "{":
            depth += 1
        elif t[j] == "}":
            depth -= 1
            if depth == 0:
                try:
                    return json.loads(t[i:j + 1])
                except Exception:
                    return None
    return None


# ════════════════════════════ main ════════════════════════════════════
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--forecasts-only", action="store_true")
    ap.add_argument("--brief-only", action="store_true")
    args = ap.parse_args()

    slow = load("public/slow.json")
    health = load("public/health.json")
    prices = load("public/prices.json")
    radar = load("public/radar.json")
    holidays = {h[0] for h in (slow.get("holidays") or []) if h and h[2] == 1}
    sys.stderr.write(f"holidays excluded from fitting: {len(holidays)}\n")

    sys.stderr.write("forecasts\n")
    fc = build_forecasts(slow, health, holidays)
    n_series = len(fc["ridership"]) + len(fc["blood"])

    series_map = {}
    for label, block in (("ridership", (slow.get("mobility") or {}).get("rid")),
                         ("blood", (health or {}).get("don"))):
        if block and block.get("keys"):
            for k in block["keys"]:
                series_map[f"{label}/{k}"] = {"t0": block["t0"],
                                              "vals": block["series"].get(k) or []}
    hits = anomalies(series_map, holidays)
    sys.stderr.write(f"anomalies: {len(hits)} flagged\n")

    if not args.brief_only:
        # A forecasts.json with nothing in it would blank the overlay; better
        # to keep yesterday's file than publish an empty one.
        if n_series == 0:
            sys.exit("insights: no series qualified, refusing to write forecasts")
        with open(OUT_FC, "w") as f:
            json.dump(fc, f, separators=(",", ":"))
        sys.stderr.write(f"wrote {OUT_FC} ({len(open(OUT_FC).read()):,} bytes, "
                         f"{n_series} series)\n")

    if not args.forecasts_only:
        sys.stderr.write("brief\n")
        brief = build_brief(slow, health, prices, radar, fc, hits)
        brief["anomalies"] = hits[:6]
        with open(OUT_IN, "w") as f:
            json.dump(brief, f, separators=(",", ":"), ensure_ascii=False)
        sys.stderr.write(f"wrote {OUT_IN} ({len(open(OUT_IN).read()):,} bytes)\n")


if __name__ == "__main__":
    main()
