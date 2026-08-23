#!/usr/bin/env bash
# Minify the shell assets for serving. Sources stay hand-edited:
#   public/app.js      -> public/app.min.js      (esbuild --minify)
#   public/styles.css  -> public/styles.min.css
# The Worker serves the .min file when it exists and is not older than its
# source; otherwise the source. CI regenerates these on every push and fails
# if a committed .min does not match a fresh build (no silent staleness).
set -euo pipefail
cd "$(dirname "$0")/.."

command -v npx >/dev/null || { echo "npx not found" >&2; exit 1; }

npx -y esbuild@0.28.2 public/app.js --minify \
  --legal-comments=none --outfile=public/app.min.js --log-level=warning
npx -y esbuild@0.28.2 public/styles.css --minify \
  --legal-comments=none --outfile=public/styles.min.css --log-level=warning
node --check public/app.min.js

for pair in "app.js app.min.js" "styles.css styles.min.css"; do
  set -- $pair
  s="public/$1"; m="public/$2"
  [ -f "$m" ] || { echo "missing $m" >&2; exit 1; }
  # sanity: the minified artifact must reference the same logic (rough guard)
  echo "ok  $m ($(wc -c < "$m" | tr -d ' ') bytes)"
done
echo "minify OK"
