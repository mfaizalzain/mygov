#!/usr/bin/env python3
"""Upload / download mygov collector data to Cloudflare KV.

Collectors (slow / health / radar) write JSON into public/ and, instead of
committing to git (which caused constant push races with manual edits), push
the data straight to KV. The Worker serves the KV copy with a static-file
fallback.

Modes:
  push [keys...] [--snap]
                  Upload public/{slow,health,radar,prices,geo}.json + feed.xml to
                  KV. Naming one or more keys restricts the upload to those.
                  Do that whenever a workflow regenerates only part of the set:
                  an unfiltered push also re-uploads the *git-committed* copies
                  of the files it did not touch, clobbering fresher KV values
                  written by another collector.
                  --snap also builds the SEO snapshot from embed_seo.snapshot()
                  and uploads it as the 'seo_snap' key (index.html splice).
  pull <key> <dest>  Download a KV key into a local file (used by the radar
                  collector to fetch its 7-day history before running).

Env:
  CF_API_TOKEN    Cloudflare API token (Workers KV Storage: Edit).
  CF_ACCOUNT_ID   Cloudflare account id.
  KV_NAMESPACE_ID Optional; defaults to the mygov namespace id below.
"""
import json
import os
import sys
import urllib.error
import urllib.request

NAMESPACE_ID = "40812fc5fedb4e1fb66d70f75e707f90"  # MYGOV_DATA
BASE = "https://api.cloudflare.com/client/v4"
FILES = {
    "slow": "public/slow.json",
    "health": "public/health.json",
    "radar": "public/radar.json",
    "prices": "public/prices.json",
    "geo": "public/geo.json",
    "feed": "public/feed.xml",
}


def api(method, path, body=None):
    token = os.environ.get("CF_API_TOKEN", "")
    account = os.environ.get("CF_ACCOUNT_ID", "")
    ns = os.environ.get("KV_NAMESPACE_ID", NAMESPACE_ID)
    if not token or not account:
        sys.exit("kv: CF_API_TOKEN and CF_ACCOUNT_ID must be set")
    url = f"{BASE}/accounts/{account}/storage/kv/namespaces/{ns}/{path}"
    req = urllib.request.Request(url, method=method)
    req.add_header("Authorization", f"Bearer {token}")
    if body is not None:
        req.add_header("Content-Type", "application/json")
        req.data = body if isinstance(body, bytes) else body.encode("utf-8")
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            raw = r.read().decode("utf-8", "replace")
            # PUT/GET envelope vs raw value: KV returns the raw value as the
            # response body for value GETs. Try JSON first; fall back to raw.
            if not raw:
                return ""
            try:
                return json.loads(raw)
            except ValueError:
                return raw
    except urllib.error.HTTPError as e:
        sys.exit(f"kv: {method} {path} -> HTTP {e.code}: {e.read().decode('utf-8','replace')[:300]}")


def put(key, value):
    resp = api("PUT", f"values/{key}", value)
    if isinstance(resp, dict) and not resp.get("success"):
        sys.exit(f"kv: upload {key} failed: {resp.get('errors')}")
    print(f"kv: uploaded {key} ({len(value)} bytes)")


def push(include_snap=False, only=None):
    for key, path in FILES.items():
        if only and key not in only:
            continue
        try:
            with open(path, encoding="utf-8") as f:
                put(key, f.read())
        except OSError as e:
            print(f"kv: skip {path}: {e}")
    if include_snap:
        try:
            sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
            import embed_seo
            radar = embed_seo.load("public/radar.json")
            health = embed_seo.load("public/health.json")
            slow = embed_seo.load("public/slow.json")
            lines = embed_seo.snapshot(radar, health, slow)
            if lines:
                put("seo_snap", "\n".join(lines))
            else:
                print("kv: seo_snap skipped - no snapshot lines")
        except Exception as e:
            print(f"kv: seo_snap failed: {e}")


def pull(key, dest):
    resp = api("GET", f"values/{key}")
    if isinstance(resp, dict) and not resp.get("success"):
        sys.exit(f"kv: pull {key} failed: {resp.get('errors')}")
    raw = resp if isinstance(resp, str) else json.dumps(resp)
    with open(dest, "w", encoding="utf-8") as f:
        f.write(raw)
    print(f"kv: pulled {key} -> {dest} ({len(raw)} bytes)")


if __name__ == "__main__":
    args = sys.argv[1:]
    if args and args[0] == "push":
        only = [a for a in args[1:] if not a.startswith("--")]
        unknown = [k for k in only if k not in FILES]
        if unknown:
            sys.exit(f"kv: unknown key(s) {unknown}; known: {sorted(FILES)}")
        push(include_snap="--snap" in args, only=only or None)
    elif args and args[0] == "pull" and len(args) == 3:
        pull(args[1], args[2])
    else:
        sys.exit(__doc__)
