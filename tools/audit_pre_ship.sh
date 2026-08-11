#!/bin/bash
# Pre-ship security audit: scan working tree for secrets + em/en dashes
cd "$(dirname "$0")/.." || exit 1
echo "=== secrets scan (working tree) ==="
grep -rnE "(ghp_|github_pat_|AIza[0-9A-Za-z_-]{20,}|sk-[A-Za-z0-9]{20,}|-----BEGIN [A-Z ]*PRIVATE KEY-----|AC_PASSWORD|api[_-]?key[[:space:]]*[:=][[:space:]]*['\"][^'\"]{16,})" \
  --include="*.py" --include="*.js" --include="*.yml" --include="*.json" --include="*.md" . 2>/dev/null \
  | grep -v node_modules | grep -v "\.git/" | head -10
echo "(clean if empty)"
echo "=== em/en dash scan ==="
python3 - <<'PY'
import re
for f in ['README.md', 'public/index.html', 'public/sw.js', 'src/index.js', 'docs/', '.hermes/plans/']:
    if f.endswith('/'):
        import os
        for root, _, files in os.walk(f):
            for fn in files:
                p = os.path.join(root, fn)
                try:
                    t = open(p, encoding='utf-8').read()
                except Exception:
                    continue
                bad = re.findall(r'[\u2013\u2014]', t)
                if bad:
                    print(p, len(bad), 'dashes')
    else:
        t = open(f, encoding='utf-8').read()
        bad = re.findall(r'[\u2013\u2014]', t)
        print(f, len(bad), 'dashes' if bad else 'clean')
PY
