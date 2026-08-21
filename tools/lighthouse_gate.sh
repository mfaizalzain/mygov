#!/usr/bin/env bash
# Lighthouse pre-ship gate for mygov.
#
# Usage: bash tools/lighthouse_gate.sh [base-url]   (default http://127.0.0.1:8788)
#
# Runs Lighthouse (mobile, the strict preset) against the given base URL and
# FAILS (exit 1) unless every category meets the floor. Part of the MANDATORY
# pre-ship gate - a UI change that ships without this repeating the 2026-08-21
# regression (perf silently fell 98 -> 63 in production).
#
# Floors (2026-08-21, Phase-0 baseline):
#   performance >= 90 mobile, CLS <= 0.05, accessibility/BP/SEO = 100.
# Desktop spot-checks are manual: --preset=desktop against the same URL.
set -uo pipefail

BASE="${1:-http://127.0.0.1:8788}"
CHROME_BIN="${CHROME_PATH:-/Applications/Google Chrome.app/Contents/MacOS/Google Chrome}"
OUT="$(mktemp -t lh-gate.XXXXXX.json)"

command -v npx >/dev/null || { echo "npx not found"; exit 1; }
[ -x "$CHROME_BIN" ] || { echo "Chrome not found at $CHROME_BIN"; exit 1; }

echo "Lighthouse gate vs $BASE ..."
CHROME_PATH="$CHROME_BIN" npx -y lighthouse@12 "$BASE/?gate=$(date +%s)" \
  --quiet --chrome-flags="--headless=new" \
  --only-categories=performance,accessibility,best-practices,seo \
  --output=json --output-path="$OUT" --max-wait-for-load=60000

python3 - "$OUT" <<'PY'
import json, sys

with open(sys.argv[1]) as f:
    lh = json.load(f)

cats = {c: d["score"] for c, d in lh["categories"].items()}
A = lh["audits"]
cls_raw = A["cumulative-layout-shift"].get("numericValue", 0) or 0
lcp_ms = A["largest-contentful-paint"].get("numericValue", 0) or 0

def pct(x): return round((x or 0) * 100)
print(f"performance {pct(cats.get('performance'))} | accessibility {pct(cats.get('accessibility'))} "
      f"| best-practices {pct(cats.get('best-practices'))} | seo {pct(cats.get('seo'))} "
      f"| CLS {cls_raw:.4f} | LCP {lcp_ms/1000:.1f}s")

fails = []
if pct(cats.get("performance")) < 90:            fails.append("performance < 90")
if cls_raw > 0.05:                               fails.append(f"CLS {cls_raw:.3f} > 0.05")
if pct(cats.get("accessibility")) < 100:         fails.append("accessibility < 100")
if pct(cats.get("best-practices")) < 100:        fails.append("best-practices < 100")
if pct(cats.get("seo")) < 100:                   fails.append("seo < 100")

for f_ in fails:
    print("GATE FAIL:", f_)
print("GATE PASS" if not fails else "GATE FAILED")
sys.exit(1 if fails else 0)
PY
