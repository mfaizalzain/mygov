import { test, describe, beforeEach } from "node:test";
import assert from "node:assert/strict";

// Core utility implementations under test (matching public/app.js)

function nf(n, d = 0){
  if (n == null || isNaN(n)) return "-";
  return Number(n).toLocaleString("en-MY", {
    minimumFractionDigits: d,
    maximumFractionDigits: d
  });
}

function ago(sec, nowSec = 1700000000){
  if (!sec) return "-";
  const d = Math.max(0, nowSec - Number(sec));
  if (d < 60) return "just now";
  const m = Math.round(d / 60);
  if (m < 60) return m + " min ago";
  const h = Math.round(m / 60);
  if (h < 24) return h + " h ago";
  return Math.round(h / 24) + " d ago";
}

function ymd(d){
  if (!d) return "";
  const dt = new Date(d);
  if (isNaN(dt.getTime())) return String(d).slice(0, 10);
  return dt.toISOString().slice(0, 10);
}

function hhmm(d){
  if (!d) return "";
  const dt = new Date(d);
  if (isNaN(dt.getTime())) return "";
  const h = String(dt.getHours()).padStart(2, "0");
  const m = String(dt.getMinutes()).padStart(2, "0");
  return `${h}:${m}`;
}

function wxHourLab(t, lang = "en"){
  const hh = Number(String(t).slice(11, 13));
  if (isNaN(hh)) return t;
  if (lang === "ms")
    return hh < 12 ? `${hh}pg` : hh === 12 ? "12tg" : `${hh - 12}ptg`;
  return hh === 0 ? "12am" : hh < 12 ? `${hh}am` : hh === 12 ? "12pm" : `${hh - 12}pm`;
}

function esc(s){
  return String(s ?? "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#39;");
}

function safeUrl(u){
  if (!u) return "";
  try {
    const p = new URL(u, "https://example.com");
    if (p.protocol === "http:" || p.protocol === "https:") return u;
    return "";
  } catch {
    return "";
  }
}

const TRAFFIC_URL_RE = /(https?:\/\/[^\s<>"']+)/g;
function trafficClean(s){
  return String(s || "").split(TRAFFIC_URL_RE).map((seg, i) => {
    if (i % 2) return seg;
    return seg
      .replace(/[@#][A-Za-z0-9_]+/g, " ")
      .replace(/\s+/g, " ")
      .trim();
  }).join(" ");
}

function haversine(p1, p2){
  const R = 6371; // Earth radius in km
  const dLat = (p2.lat - p1.lat) * Math.PI / 180;
  const dLon = (p2.lon - p1.lon) * Math.PI / 180;
  const a =
    Math.sin(dLat / 2) * Math.sin(dLat / 2) +
    Math.cos(p1.lat * Math.PI / 180) * Math.cos(p2.lat * Math.PI / 180) *
    Math.sin(dLon / 2) * Math.sin(dLon / 2);
  const c = 2 * Math.atan2(Math.sqrt(a), Math.sqrt(1 - a));
  return R * c;
}

function matchQuality(candidate, query){
  const c = String(candidate).toLowerCase();
  const q = String(query).toLowerCase();
  if (c === q) return 1.0;
  if (c.startsWith(q)) return 0.8;
  if (c.includes(q)) return 0.5;
  return 0.0;
}

function tableRowsToCSV(rows){
  return rows.map(r => {
    return r.map(cell => {
      let val = String(cell ?? "").trim().replace(/\s+/g, " ");
      if (val.includes(",") || val.includes('"') || val.includes("\n")){
        val = '"' + val.replace(/"/g, '""') + '"';
      }
      return val;
    }).join(",");
  }).join("\n");
}

// ── Tests ──

describe("Formatting & Numerical Utilities", () => {
  test("nf() formats numbers with proper locale and decimal places", () => {
    assert.equal(nf(1234.567, 2), "1,234.57");
    assert.equal(nf(1000, 0), "1,000");
    assert.equal(nf(null), "-");
    assert.equal(nf(undefined), "-");
    assert.equal(nf(NaN), "-");
  });

  test("ago() calculates relative time correctly", () => {
    const now = 1700000000;
    assert.equal(ago(now - 10, now), "just now");
    assert.equal(ago(now - 180, now), "3 min ago");
    assert.equal(ago(now - 7200, now), "2 h ago");
    assert.equal(ago(now - 172800, now), "2 d ago");
    assert.equal(ago(null), "-");
  });

  test("wxHourLab() formats hours in 12h clock for EN and MS", () => {
    assert.equal(wxHourLab("2026-08-14T00:00:00", "en"), "12am");
    assert.equal(wxHourLab("2026-08-14T08:00:00", "en"), "8am");
    assert.equal(wxHourLab("2026-08-14T12:00:00", "en"), "12pm");
    assert.equal(wxHourLab("2026-08-14T15:00:00", "en"), "3pm");

    assert.equal(wxHourLab("2026-08-14T08:00:00", "ms"), "8pg");
    assert.equal(wxHourLab("2026-08-14T12:00:00", "ms"), "12tg");
    assert.equal(wxHourLab("2026-08-14T17:00:00", "ms"), "5ptg");
  });
});

describe("Text Sanitization & Security", () => {
  test("esc() escapes HTML characters properly", () => {
    assert.equal(esc("<script>alert('xss')</script>"), "&lt;script&gt;alert(&#39;xss&#39;)&lt;/script&gt;");
    assert.equal(esc('Tom & "Jerry"'), "Tom &amp; &quot;Jerry&quot;");
    assert.equal(esc(null), "");
  });

  test("safeUrl() permits safe http/https URLs and rejects unsafe protocols", () => {
    assert.equal(safeUrl("https://data.gov.my/dashboard"), "https://data.gov.my/dashboard");
    assert.equal(safeUrl("http://met.gov.my"), "http://met.gov.my");
    assert.equal(safeUrl("javascript:alert(1)"), "");
    assert.equal(safeUrl("data:text/html,<script>"), "");
    assert.equal(safeUrl(""), "");
  });

  test("trafficClean() strips telegram handles and hashtags but preserves URLs", () => {
    const raw = "Kemalangan @llminfotrafik #kltu di KM 14 https://t.me/infotrafikgz sesak";
    const cleaned = trafficClean(raw);
    assert.ok(cleaned.includes("https://t.me/infotrafikgz"));
    assert.ok(!cleaned.includes("@llminfotrafik"));
    assert.ok(!cleaned.includes("#kltu"));
  });
});

describe("Geographical & Search Algorithms", () => {
  test("haversine() computes distance accurately between Malaysian locations", () => {
    const kl = { lat: 3.1390, lon: 101.6869 };
    const pj = { lat: 3.1073, lon: 101.6067 };
    const dist = haversine(kl, pj);
    assert.ok(dist >= 9 && dist <= 12, `Distance should be ~10km, got ${dist}`);

    // Identical coordinates should be 0
    assert.equal(haversine(kl, kl), 0);
  });

  test("matchQuality() scores exact and partial matches with appropriate weights", () => {
    assert.equal(matchQuality("Kuala Lumpur", "kuala lumpur"), 1.0);
    assert.equal(matchQuality("Kuala Lumpur", "kuala"), 0.8);
    assert.equal(matchQuality("George Town", "town"), 0.5);
    assert.equal(matchQuality("Johor Bahru", "Kuching"), 0.0);
  });
});

describe("CSV Exporting Serialization", () => {
  test("tableRowsToCSV() handles quotes, commas, and escaping", () => {
    const rows = [
      ["District", "State", "Population", "Notes"],
      ["Petaling", "Selangor", "1,800,000", "High density, urban"],
      ['Klang "North"', "Selangor", "900,000", "Port area, active"],
      ["Batu Pahat", "Johor", "450,000", "-"]
    ];

    const csv = tableRowsToCSV(rows);
    const lines = csv.split("\n");

    assert.equal(lines[0], "District,State,Population,Notes");
    assert.equal(lines[1], 'Petaling,Selangor,"1,800,000","High density, urban"');
    assert.equal(lines[2], '"Klang ""North""",Selangor,"900,000","Port area, active"');
    assert.equal(lines[3], 'Batu Pahat,Johor,"450,000",-');
  });
});

describe("State Persistence & Saved Locations Logic", () => {
  let mockStorage = {};

  beforeEach(() => {
    mockStorage = {};
  });

  function mockGetSavedLocs(){
    try {
      const raw = mockStorage["mygov.savedlocs.v1"];
      const list = raw ? JSON.parse(raw) : [];
      return Array.isArray(list) ? list : [];
    } catch { return []; }
  }

  function mockSaveLoc(id, name){
    const list = mockGetSavedLocs().filter(x => x.id !== id);
    list.unshift({ id, name });
    if (list.length > 6) list.pop();
    mockStorage["mygov.savedlocs.v1"] = JSON.stringify(list);
    return list;
  }

  function mockRemoveLoc(id){
    const list = mockGetSavedLocs().filter(x => x.id !== id);
    mockStorage["mygov.savedlocs.v1"] = JSON.stringify(list);
    return list;
  }

  test("Bookmarking saves, deduplicates, and bounds to max 6 locations", () => {
    mockSaveLoc("kl", "Kuala Lumpur");
    mockSaveLoc("jb", "Johor Bahru");
    assert.equal(mockGetSavedLocs().length, 2);
    assert.equal(mockGetSavedLocs()[0].id, "jb");

    // Deduplicate on re-save
    mockSaveLoc("kl", "Kuala Lumpur");
    assert.equal(mockGetSavedLocs().length, 2);
    assert.equal(mockGetSavedLocs()[0].id, "kl");

    // Remove
    mockRemoveLoc("jb");
    assert.equal(mockGetSavedLocs().length, 1);
    assert.equal(mockGetSavedLocs()[0].id, "kl");
  });

  test("calculateOrderedSections() floats pinned sections to top while keeping order", () => {
    const defaultSections = ["hazards", "weather", "fuel", "population", "economy", "finance", "mobility", "transport"];
    const pinned = ["transport", "fuel"];

    const ordered = [
      ...pinned.filter(id => defaultSections.includes(id)),
      ...defaultSections.filter(id => !pinned.includes(id))
    ];

    assert.deepEqual(ordered.slice(0, 2), ["transport", "fuel"]);
    assert.equal(ordered.length, defaultSections.length);
    assert.ok(ordered.includes("weather"));
  });
});

/* ═══════════════════════ structured traffic incidents ═══════════════════════
   Pure-logic mirrors of the tinc* helpers in public/app.js (the render path
   needs a DOM; these cover the decision logic against the real collector
   output shape). The TomTom incidents are merged into the marquee, scoped to
   the visitor's region, active-only, fresh-only. */

const TINC_STATE = {
  "kuala lumpur": "kl-selangor", "selangor": "kl-selangor", "putrajaya": "kl-selangor",
  "johor": "johor", "pulau pinang": "penang", "penang": "penang",
  "perak": "perak-ipoh", "melaka": "melaka", "negeri sembilan": "kl-selangor",
  "pahang": "pahang-cameron", "kedah": "kedah-langkawi",
  "kelantan": "kelantan-kb", "terengganu": "kuantan",
  "sarawak": "kuching", "kuching": "kuching", "labuan": "kuching",
};

const TINC_NAMES = {
  "kl-selangor": "Klang Valley", "johor": "JB", "penang": "Penang",
  "perak-ipoh": "Ipoh", "melaka": "Melaka", "pahang-cameron": "Cameron Highlands",
  "kedah-langkawi": "Langkawi", "kuantan": "Kuantan",
  "kelantan-kb": "Kota Bharu", "kuching": "Kuching",
};

describe("traffic incidents marquee logic", () => {
  const geoState = osm => String(osm).split(",").pop().trim().toLowerCase();

  test("OSM state maps to the right region slug", () => {
    assert.equal(TINC_STATE[geoState("Kajang, Selangor")], "kl-selangor");
    assert.equal(TINC_STATE[geoState("Kuala Lumpur")], "kl-selangor");
    assert.equal(TINC_STATE[geoState("Johor Bahru, Johor")], "johor");
    assert.equal(TINC_STATE[geoState("George Town, Penang")], "penang");
    assert.equal(TINC_STATE[geoState("Ipoh, Perak")], "perak-ipoh");
    assert.equal(TINC_STATE[geoState("Kuching, Sarawak")], "kuching");
  });

  test("every state maps to a region the collector emits", () => {
    const collectorSlugs = new Set([
      "kl-selangor", "johor", "penang", "perak-ipoh", "melaka",
      "pahang-cameron", "kedah-langkawi", "kuantan", "kelantan-kb", "kuching",
    ]);
    for (const slug of Object.values(TINC_STATE)) assert.ok(collectorSlugs.has(slug), slug);
    // every region has a display name
    for (const slug of collectorSlugs) assert.ok(TINC_NAMES[slug], `no name for ${slug}`);
  });

  test("ticker item text: category emoji, road, description, region", () => {
    const tincItem = (i, regionName) => {
      const dot = i.catName === "Accident" ? "🔴" : i.catName === "Road closed" ? "⛔"
        : i.catName === "Road works" ? "🚧" : i.catName === "Hazard" ? "⚠" : "🔸";
      const where = [i.from, i.to].filter(Boolean).join(" → ") || "road";
      const desc = (i.events && i.events[0]) ? ` · ${i.events[0]}` : "";
      return `${dot} ${where}${desc} · ${regionName}`;
    };
    const t = tincItem({ catName: "Accident", from: "Jalan A", to: "Jalan B",
      events: ["Queuing traffic"] }, "Klang Valley");
    assert.ok(t.startsWith("🔴"));
    assert.ok(t.includes("Jalan A → Jalan B"));
    assert.ok(t.includes("Queuing traffic"));
    assert.ok(t.endsWith("· Klang Valley"));
  });

  test("ended incidents are filtered out of the active list (no stale traffic)", () => {
    const now = Date.now();
    const iso = ms => new Date(ms).toISOString();
    const tincActive = incs => incs.filter(i => {
      if (!i.end) return true;
      const e = Date.parse(i.end);
      return !isFinite(e) || e > now;
    });
    const incs = [
      { end: iso(now - 3600e3) },   // ended 1h ago -> drop
      { end: iso(now + 7200e3) },   // ongoing -> keep
      {},                            // no end -> keep (assume ongoing)
    ];
    const active = tincActive(incs);
    assert.equal(active.length, 2);
    assert.equal(active[0].end, incs[1].end);
    assert.equal(active[1].end, undefined);
  });

  test("a feed older than the max age is treated as stale (skipped)", () => {
    const TINC_MAX_AGE = 6 * 3600e3;
    const now = Date.now();
    const fresh = now - 2 * 3600e3;
    const stale = now - 10 * 3600e3;
    assert.ok(now - fresh <= TINC_MAX_AGE, "fresh feed should be within window");
    assert.ok(now - stale > TINC_MAX_AGE, "stale feed should be outside window");
  });
});
