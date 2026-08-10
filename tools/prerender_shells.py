#!/usr/bin/env python3
"""Generate static section shells + KPI skeletons for mygov index.html.

Splices pre-rendered markup into <main> so the page has its full height at
first paint (kills the 0.93 CLS from buildShell() injecting sections late).
Also pre-renders the radar band visible with a skeleton and the 6 KPI cards
in their loading state.

Usage: python3 tools/prerender_shells.py  (idempotent; safe to re-run)
"""
import io, re, sys

P = "public/index.html"
src = io.open(P, encoding="utf-8").read()

# ── extract SECTIONS + META from the inline script ──────────────────────
m = re.search(r"const SECTIONS = (\[.*?\n\]);", src, re.S)
if not m:
    sys.exit("SECTIONS not found")
sections = []
for sm in re.finditer(r"\{\s*id:\"(\w+)\",\s*label:\"([^\"]+)\",\s*icon:\"(\w+)\",\s*family:\"([^\"]+)\"\s*\}", m.group(1)):
    sections.append({"id": sm.group(1), "label": sm.group(2), "icon": sm.group(3)})

mm = re.search(r"const META = (\{.*?\n\});", src, re.S)
if not mm:
    sys.exit("META not found")
meta_block = mm.group(1)
meta = {}
for km in re.finditer(r"(\w+):\{\s*title:\"([^\"]*)\",\s*desc:\"([^\"]*)\",\s*how:\"([^\"]*)\",\s*eps:\[(.*?)\]\s*\}", meta_block, re.S):
    eps = re.findall(r"\"([^\"]+)\"", km.group(5))
    meta[km.group(1)] = {"title": km.group(2), "desc": km.group(3), "how": km.group(4), "eps": eps}

def esc(s):
    return (s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
             .replace('"', "&quot;"))

# ── build section shells ────────────────────────────────────────────────
# the skeleton every section body shows while its loader runs; pre-rendering
# it statically keeps the body height stable from first paint (no CLS when
# the loader replaces it with the identical skeleton, and the real content
# swaps in at roughly the same footprint).
SKEL = ('<div class="card"><div class="card-b">'
        '<div class="skel" style="width:94%"></div><div class="skel" style="width:72%"></div>'
        '<div class="skel" style="width:86%"></div><div class="skel" style="width:60%"></div>'
        '<div class="skel skel-chart"></div>'
        '</div></div>')

# the eager above-fold sections get a taller skeleton that mirrors their real
# card layout (same cards/classes/breakpoints) so the skeleton->content swap
# happens inside the same footprint (no CLS). Keep in sync with skeleton().
def bars(k):
    return "".join(f'<div class="skel" style="width:{[94,72,86,60][i%4]}%"></div>' for i in range(k))
SKEL_WEATHER = ('<div class="mb"><div class="card"><div class="card-h"><div class="skel" style="width:32%"></div></div>'
      '<div class="card-b">' + bars(2) + '</div></div></div>'
      '<div class="grid g2 mb">'
      '<div class="card"><div class="card-h"><div class="skel" style="width:38%"></div></div>'
      '<div class="card-b"><div class="skel skel-chart"></div><div class="skel skel-table"></div></div></div>'
      '<div class="card"><div class="card-h"><div class="skel" style="width:42%"></div></div>'
      '<div class="card-b">' + bars(2) + '<div class="skel skel-table"></div></div></div>'
      '</div>'
      '<div class="card"><div class="card-h"><div class="skel" style="width:30%"></div></div>'
      '<div class="card-b">' + bars(2) + '<div class="skel skel-table"></div></div></div>')
SKEL_FUEL = ('<div class="grid g2 mb">'
      '<div class="card"><div class="card-h"><div class="skel" style="width:40%"></div></div>'
      '<div class="card-b"><div class="skel skel-chart"></div><div class="skel skel-table"></div></div></div>'
      '<div class="card"><div class="card-h"><div class="skel" style="width:34%"></div></div>'
      '<div class="card-b">' + bars(3) + '<div class="skel skel-table"></div></div></div>'
      '</div>'
      '<div class="card"><div class="card-h"><div class="skel" style="width:28%"></div></div>'
      '<div class="card-b">' + bars(3) + '<div class="skel skel-table"></div></div></div>')
SHELL_SKELS = {"weather": SKEL_WEATHER, "fuel": SKEL_FUEL}
shells = []
for s in sections:
    meta_s = meta.get(s["id"], {})
    eps = "".join(f'<li><code>GET {esc(e)}</code></li>' for e in meta_s.get("eps", []))
    shells.append(f'''    <section id="{s["id"]}" aria-labelledby="h-{s["id"]}">
      <div class="sec-h">
        <div class="sec-ico" aria-hidden="true"><svg class="ico" style="width:20px;height:20px" aria-hidden="true" focusable="false"><use href="#i-{s["icon"]}"/></svg></div>
        <div><h3 id="h-{s["id"]}">{esc(meta_s.get("title", s["label"]))}</h3>
          <p>{esc(meta_s.get("desc", ""))}</p>
          <details class="meta">
            <summary>Data source &amp; methodology</summary>
            <p>{esc(meta_s.get("how", ""))}</p>
            <ul>{eps}</ul>
          </details>
        </div>
        <span class="sec-time" id="time-{s["id"]}"></span>
      </div>
      <div id="body-{s["id"]}">{SHELL_SKELS.get(s["id"], SKEL)}</div>
    </section>''')

shell_html = "\n".join(shells)

# ── KPI skeleton cards (exact markup renderKpis produces pre-data) ──────
KPIS = [
    ("hot", "Hottest today", "temp", "#weather"),
    ("ron95", "RON 95", "fuel", "#fuel"),
    ("basket", "Groceries y/y", "basket", "#prices"),
    ("cpi", "Inflation y/y", "economy", "#economy"),
    ("ev", "New EVs", "ev", "#mobility"),
    ("warn", "Active warnings", "warn", "#weather"),
    ("live", "Vehicles live", "bus", "#live"),
]
kpi_cards = "\n".join(
    f'''      <a class="kpi kpi-load" href="{href}" aria-label="{lab} - go to the {href.lstrip("#")} section">
        <div class="kpi-t"><span class="lab"><svg class="ico" aria-hidden="true" focusable="false"><use href="#i-{ico}"/></svg> {lab}</span>
          <span class="go" aria-hidden="true">↗</span></div>
        <div class="val" id="kpi-{k}"><span class="skel skel-val"></span></div>
        <div class="sub"><span class="skel skel-sub"></span></div></a>'''
    for k, lab, ico, href in KPIS)

# ── radar band: visible with a skeleton track (no late unhide) ──────────
radar_new = '''  <section class="radar-band" id="radar-band" aria-labelledby="radar-h">
    <div class="radar-band-h">
      <div class="radar-band-t">
        <div class="sec-ico" aria-hidden="true"><svg class="ico" style="width:20px;height:20px" aria-hidden="true" focusable="false"><use href="#i-flame"/></svg></div>
        <div>
          <h3 id="radar-h" data-i18n="Trend Radar">Trend Radar</h3>
          <p data-i18n="The hottest issues and viral claims circulating in Malaysia right now - each verified against real sources.">The hottest issues and viral claims circulating in Malaysia right now - each verified against real sources.</p>
        </div>
      </div>
      <div class="radar-band-ctl">
        <span class="radar-count" id="radar-count" aria-live="polite"></span>
        <button class="btn" id="radar-prev" aria-label="Previous issues">‹</button>
        <button class="btn" id="radar-next" aria-label="Next issues">›</button>
      </div>
    </div>
    <div class="radar-track" id="radar-track" tabindex="0" aria-label="Trending issues carousel">
      <div class="card" style="flex:0 0 320px;min-height:200px"><div class="card-b">
        <div class="skel" style="width:86%"></div><div class="skel" style="width:64%"></div>
        <div class="skel" style="width:72%"></div>
      </div></div>
    </div>
  </section>'''

# ── nav entries (pre-rendered so the nav has its full height at first paint) ──
def nav_item(sid, label, icon, dot=True):
    d = f'<span class="dot" id="dot-{sid}"></span>' if dot else ""
    return (f'    <li><a href="#{sid}" id="nav-{sid}">{d}'
            f'<svg class="ico" aria-hidden="true" focusable="false"><use href="#i-{icon}"/></svg> {esc(label)}</a></li>')
NAV_ITEMS = "".join(
    [f'    <li hidden><a href="#radar-band" id="nav-radar-band"><svg class="ico" aria-hidden="true" focusable="false"><use href="#i-flame"/></svg> Trending</a></li>\n']
    + [nav_item(s["id"], s["label"], s["icon"]) + "\n" for s in sections])

# ── hero-loc pre-render: the idle "use my location" button occupies the same
#    slot the geo chip will take, so the row never re-wraps when JS fills it ──
HERO_LOC = ('<div class="hero-loc" id="hero-loc" role="status" aria-label="Your selected location">'
            '<button class="btn btn-a" id="hero-loc-try">'
            '<svg class="ico" aria-hidden="true" focusable="false"><use href="#i-live"/></svg> '
            '<span data-i18n="use my location">use my location</span></button></div>')

# ── splice ──────────────────────────────────────────────────────────────
# 0. navlist gets the pre-rendered entries
src = src.replace('<ul id="navlist"></ul>', '<ul id="navlist">\n' + NAV_ITEMS + '  </ul>', 1)

# 0b. hero-loc gets the idle button (empty div -> CLS when JS fills it)
src = re.sub(r'<div class="hero-loc" id="hero-loc" role="status" aria-label="Your selected location"></div>',
             HERO_LOC, src, count=1)

# 1. main gets shells before the noscript block
#    (idempotent: remove any shells spliced by an earlier run first)
src = re.sub(r'(<main id="main">)\s*(?:    <section id="[^"]+"[^>]*>.*?</section>\n)+',
             r'\1\n', src, count=1, flags=re.S)
main_m = re.search(r'(<main id="main">)(\s*)(<!-- Static fallback)', src)
if not main_m:
    sys.exit("main marker not found")
# Resume at group 3 (the comment), NOT group 2 (the whitespace before it):
# group 2 already starts with the newline this splice emits, so carrying it
# over appended one blank line per run - the script drifted every time it was
# re-run despite the "idempotent" promise above. The four-space indent is
# re-emitted here so the comment keeps its original position.
src = (src[:main_m.start()] + '<main id="main">\n' + shell_html + "\n    "
       + src[main_m.start(3):])

# 2. kpis div gets the skeleton cards
src = re.sub(r'(<div class="kpis" id="kpis"></div>)',
             '<div class="kpis" id="kpis">\n' + kpi_cards + "\n    </div>", src, count=1)

# 3. radar band: replace the hidden section with the visible skeleton version
src = re.sub(r'  <section class="radar-band" id="radar-band" hidden.*?</section>\n',
             radar_new + "\n", src, count=1, flags=re.S)

io.open(P, "w", encoding="utf-8").write(src)
print(f"shells: {len(sections)} sections, {len(meta)} meta, {len(KPIS)} KPI cards spliced")
