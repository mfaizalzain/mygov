#!/usr/bin/env python3
"""Generate static section shells for mygov index.html.

Splices pre-rendered markup into <main> so the page has its full height at
first paint (kills the 0.93 CLS from buildShell() injecting sections late).
Also pre-renders the radar band visible with a skeleton. (The hero KPI strip
this script used to splice is gone - Travel Outlook holds that slot, and its
shell is hand-written in the hero.)

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
# The hazards strip is three short tiles, so its skeleton must be three short
# tiles - the generic card skeleton would reserve five screens for a section
# that is normally one row, and the page would visibly collapse on load.
SKEL_HAZARDS = ('<div class="hz-strip">' + (
      '<div class="hz-tile"><div class="card-b">'
      '<div class="skel" style="width:70%"></div>'
      '<div class="skel" style="width:46%"></div></div></div>') * 3 + '</div>')
SHELL_SKELS = {"weather": SKEL_WEATHER, "fuel": SKEL_FUEL, "hazards": SKEL_HAZARDS}
def sub_block(sid, icon):
    """A merged sub-block, the same pattern as FLOOD_SUB: groceries rides in
    the Household section and the Places explorer rides in Population. The
    parent loader's after-hook fires loadSection(sid); the block keeps its
    own header, time pill and body so caching/KPI/error handling work.
    data-i18n keys translate it (the main section headers are handled by the
    SECTIONS loop in applyLang instead)."""
    m = meta.get(sid, {})
    title = m.get("title", sid)
    desc = m.get("desc", "")
    how = m.get("how", "")
    eps = "".join(f'<li><code>GET {esc(e)}</code></li>' for e in m.get("eps", []))
    return f'''      <!-- {title}: a merged sub-block of its parent section. -->
      <div class="sec-sub" id="{sid}-sub" aria-labelledby="h-{sid}">
        <div class="sec-h">
          <div class="sec-ico" aria-hidden="true"><svg class="ico" style="width:20px;height:20px" aria-hidden="true" focusable="false"><use href="#i-{icon}"/></svg></div>
          <div><h3 id="h-{sid}" style="font-size:17px" data-i18n="{title}">{esc(title)}</h3>
            <p data-i18n="{desc}">{esc(desc)}</p>
            <details class="meta">
              <summary data-i18n="Data source &amp; methodology">Data source &amp; methodology</summary>
              <p data-i18n="{how}">{esc(how)}</p>
              <ul>{eps}</ul>
            </details>
          </div>
          <span class="sec-time" id="time-{sid}"></span>
        </div>
        <div id="body-{sid}"><div class="card"><div class="card-b"><div class="skel" style="width:94%"></div><div class="skel" style="width:72%"></div><div class="skel" style="width:86%"></div><div class="skel" style="width:60%"></div><div class="skel skel-chart"></div></div></div></div>
      </div>'''
shells = []
for s in sections:
    meta_s = meta.get(s["id"], {})
    # The Places explorer merged INTO the Population section: its body is
    # #body-places, not #body-population (the old national cards are gone).
    sid_body = "places" if s["id"] == "population" else s["id"]
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
      <div id="body-{sid_body}">{SHELL_SKELS.get(s["id"], SKEL)}</div>
      {sub_block("prices", "basket") if s["id"] == "fuel" else
       sub_block("tourism", "tourism") if s["id"] == "economy" else
       sub_block("live", "live") if s["id"] == "transport" else
       sub_block("health", "health") if s["id"] == "population" else ""}
    </section>''')

shell_html = "\n".join(shells)

# ── radar band: visible with a skeleton track (no late unhide) ──────────
radar_new = '''  <section class="radar-band" id="radar-band" aria-labelledby="radar-h">
    <div class="radar-band-h">
      <div class="radar-band-t">
        <div class="sec-ico" aria-hidden="true"><svg class="ico" style="width:20px;height:20px" aria-hidden="true" focusable="false"><use href="#i-flame"/></svg></div>
        <div>
          <h3 id="radar-h" data-i18n="Trend Radar">Trend Radar</h3>
          <p id="radar-desc" data-i18n="The hottest issues and viral claims circulating in Malaysia right now - each verified against real sources.">The hottest issues and viral claims circulating in Malaysia right now - each verified against real sources.</p>
        </div>
      </div>
      <div class="radar-band-ctl">
        <span class="radar-count" id="radar-when"></span>
        <span class="radar-count" id="radar-count" aria-live="polite"></span>
        <button class="btn" id="radar-prev" aria-label="Previous issues">‹</button>
        <button class="btn" id="radar-next" aria-label="Next issues">›</button>
      </div>
    </div>
    <div class="radar-subbar">
      <div class="radar-modes" id="radar-modes" role="tablist" aria-label="Trend radar view mode">
        <button class="rm-btn active" id="rm-viral" role="tab" aria-selected="true" data-mode="viral"><span class="rm-icon" aria-hidden="true">🔥</span> <span data-i18n="Viral &amp; Fact-Checks">Viral &amp; Fact-Checks</span></button>
        <button class="rm-btn" id="rm-breaking" role="tab" aria-selected="false" data-mode="breaking"><span class="rm-icon" aria-hidden="true">⚡</span> <span data-i18n="Breaking News">Breaking News</span></button>
      </div>
      <div class="radar-filters" id="radar-filters" role="group" aria-label="Filter trend radar"></div>
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
#    Matches a populated <ul> as well as an empty one. Targeting only the
#    empty form made this a silent no-op on every run after the first, so a
#    new section's nav entry had to be hand-inserted while the script still
#    reported success.
src = re.sub(r'<ul id="navlist">.*?</ul>',
             '<ul id="navlist">\n' + NAV_ITEMS + '  </ul>', src, count=1, flags=re.S)

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

# 3. radar band: replace the hidden section with the visible skeleton version
src = re.sub(r'  <section class="radar-band" id="radar-band" hidden.*?</section>\n',
             radar_new + "\n", src, count=1, flags=re.S)

io.open(P, "w", encoding="utf-8").write(src)
print(f"shells: {len(sections)} sections, {len(meta)} meta spliced")
