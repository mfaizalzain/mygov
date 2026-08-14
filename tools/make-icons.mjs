// tools/make-icons.mjs
// Generates state-of-the-art PWA icons (PNGs and SVGs) with zero dependencies.
// Draws with 4x supersampling + box-filter downsampling for pristine anti-aliasing.
// Run: node tools/make-icons.mjs

import { deflateSync } from "node:zlib";
import { writeFileSync, mkdirSync } from "node:fs";

// ── COLOR PALETTE ──
const BG_TOP     = [14, 21, 36];     // #0e1524 deep obsidian slate
const BG_MID     = [10, 13, 20];     // #0a0d14
const BG_BOT     = [4, 6, 10];       // #04060a
const GLOW_COLOR = [45, 212, 191];   // #2dd4bf teal bloom
const TEAL_DEEP  = [13, 148, 136];   // #0d9488
const TEAL_MID   = [45, 212, 191];   // #2dd4bf
const CYAN_BRIGHT= [34, 211, 238];   // #22d3ee
const SKY_LIGHT  = [56, 189, 248];   // #38bdf8
const WHITE      = [255, 255, 255];
const BEACON_CYAN= [103, 232, 249];  // #67e8f9

const lerp = (a, b, t) => a.map((v, i) => Math.round(v + (b[i] - v) * t));
const clamp = (v, min, max) => Math.min(Math.max(v, min), max);

/** Distance from point (px, py) to line segment (x1, y1)-(x2, y2) */
function distToSegment(px, py, x1, y1, x2, y2) {
  const dx = x2 - x1, dy = y2 - y1;
  const l2 = dx * dx + dy * dy;
  if (l2 === 0) return Math.hypot(px - x1, py - y1);
  let t = ((px - x1) * dx + (py - y1) * dy) / l2;
  t = clamp(t, 0, 1);
  return Math.hypot(px - (x1 + t * dx), py - (y1 + t * dy));
}

/** Distance from point to circular arc */
function distToArc(px, py, cx, cy, radius, startAngle, endAngle) {
  const angle = Math.atan2(py - cy, px - cx);
  let normAngle = angle;
  while (normAngle < startAngle) normAngle += Math.PI * 2;
  while (normAngle > startAngle + Math.PI * 2) normAngle -= Math.PI * 2;
  
  if (normAngle >= startAngle && normAngle <= endAngle) {
    const d = Math.hypot(px - cx, py - cy);
    return Math.abs(d - radius);
  }
  // Distance to arc endpoints
  const x1 = cx + radius * Math.cos(startAngle);
  const y1 = cy + radius * Math.sin(startAngle);
  const x2 = cx + radius * Math.cos(endAngle);
  const y2 = cy + radius * Math.sin(endAngle);
  return Math.min(Math.hypot(px - x1, py - y1), Math.hypot(px - x2, py - y2));
}

/** Signed distance to rounded rectangle / squircle */
function insideRoundRect(x, y, w, h, r) {
  const dx = Math.max(Math.abs(x - w / 2) - (w / 2 - r), 0);
  const dy = Math.max(Math.abs(y - h / 2) - (h / 2 - r), 0);
  return Math.hypot(dx, dy) <= r;
}

/**
 * High-definition icon rendering with supersampling and analytical SDFs.
 */
function render(size) {
  const S = 4;                           // 4x supersampling
  const W = size * S;
  const buf = new Uint8Array(W * W * 4); // RGBA

  const put = (x, y, r, g, b, a) => {
    const i = (y * W + x) * 4;
    buf[i] = r; buf[i + 1] = g; buf[i + 2] = b; buf[i + 3] = a;
  };

  const pad = W * 0.04;
  const innerW = W - pad * 2;
  const radius = innerW * 0.235;         // Modern continuous corner squircle

  // Geometry coordinate definitions scaled to supersampled canvas
  // Emblem coordinates relative to 512 canvas:
  const scale = W / 512;

  // Continuous M Stroke Waypoints
  const leftX   = 140 * scale;
  const rightX  = 372 * scale;
  const baseY   = 350 * scale;
  const topY    = 216 * scale;
  const archRx  = 20 * scale;
  const archTop = 176 * scale;
  const midX    = 256 * scale;
  const midY    = 264 * scale;
  const strokeW = 44 * scale;
  const strokeR = strokeW / 2;

  // Radar Arc
  const radarCx = 256 * scale;
  const radarCy = 178 * scale;
  const radarR  = 58 * scale;
  const radarW  = 6.5 * scale;

  // Beacon Node
  const beaconX = 256 * scale;
  const beaconY = 154 * scale;
  const beaconR = 15 * scale;
  const beaconCoreR = 6 * scale;

  for (let y = 0; y < W; y++) {
    for (let x = 0; x < W; x++) {
      // Offset for centering the squircle
      const sx = x - pad, sy = y - pad;
      if (sx < 0 || sx >= innerW || sy < 0 || sy >= innerW || !insideRoundRect(sx, sy, innerW, innerW, radius)) {
        put(x, y, 0, 0, 0, 0);
        continue;
      }

      // 1. Background vertical gradient
      const ny = y / W;
      let bg = ny < 0.5 
        ? lerp(BG_TOP, BG_MID, ny * 2) 
        : lerp(BG_MID, BG_BOT, (ny - 0.5) * 2);

      // 2. Radial Ambient Center Glow
      const glowDist = Math.hypot(x - midX, y - (W * 0.46)) / (W * 0.55);
      if (glowDist < 1.0) {
        const glowFactor = Math.pow(1.0 - glowDist, 2.2) * 0.28;
        bg = lerp(bg, GLOW_COLOR, glowFactor);
      }

      // 3. Subtle Glassmorphic Top Specular Sheen
      const specDist = (x + y) / (W * 1.4);
      if (specDist < 0.6) {
        const specFactor = Math.pow(1.0 - specDist / 0.6, 2.0) * 0.08;
        bg = lerp(bg, WHITE, specFactor);
      }

      // Base pixel initialized
      let pr = bg[0], pg = bg[1], pb = bg[2], pa = 255;

      // 4. Subtle Glassmorphic Outer Border
      const distFromEdge = Math.min(
        Math.abs(sx), Math.abs(innerW - sx),
        Math.abs(sy), Math.abs(innerW - sy)
      );
      if (distFromEdge <= 2.5 * scale) {
        const borderFactor = (1.0 - distFromEdge / (2.5 * scale)) * 0.18;
        const bc = lerp(WHITE, CYAN_BRIGHT, y / W);
        pr = Math.round(pr + (bc[0] - pr) * borderFactor);
        pg = Math.round(pg + (bc[1] - pg) * borderFactor);
        pb = Math.round(pb + (bc[2] - pb) * borderFactor);
      }

      // 5. Radar Pulse Arc (Concentric Upper Wave)
      const rDist = distToArc(x, y, radarCx, radarCy, radarR, Math.PI * 1.15, Math.PI * 1.85);
      if (rDist <= radarW / 2) {
        const arcFactor = (1.0 - rDist / (radarW / 2)) * 0.65;
        const arcColor = lerp(TEAL_MID, CYAN_BRIGHT, (x - leftX) / (rightX - leftX));
        pr = Math.round(pr + (arcColor[0] - pr) * arcFactor);
        pg = Math.round(pg + (arcColor[1] - pg) * arcFactor);
        pb = Math.round(pb + (arcColor[2] - pb) * arcFactor);
      }

      // 6. Luminous Beacon Node
      const bDist = Math.hypot(x - beaconX, y - beaconY);
      if (bDist <= beaconR * 1.8) {
        if (bDist <= beaconCoreR) {
          const coreFactor = 1.0 - (bDist / beaconCoreR) * 0.15;
          pr = Math.round(pr + (WHITE[0] - pr) * coreFactor);
          pg = Math.round(pg + (WHITE[1] - pg) * coreFactor);
          pb = Math.round(pb + (WHITE[2] - pb) * coreFactor);
        } else if (bDist <= beaconR) {
          const glowFactor = (1.0 - (bDist - beaconCoreR) / (beaconR - beaconCoreR)) * 0.9;
          const bc = lerp(WHITE, BEACON_CYAN, (bDist - beaconCoreR) / (beaconR - beaconCoreR));
          pr = Math.round(pr + (bc[0] - pr) * glowFactor);
          pg = Math.round(pg + (bc[1] - pg) * glowFactor);
          pb = Math.round(pb + (bc[2] - pb) * glowFactor);
        } else {
          const outerGlow = Math.pow(1.0 - (bDist - beaconR) / (beaconR * 0.8), 2.0) * 0.4;
          pr = Math.round(pr + (TEAL_MID[0] - pr) * outerGlow);
          pg = Math.round(pg + (TEAL_MID[1] - pg) * outerGlow);
          pb = Math.round(pb + (TEAL_MID[2] - pb) * outerGlow);
        }
      }

      // 7. Distance to the Continuous 'M' Stroke
      // Segments:
      // S1: Left vertical stem (leftX, baseY) -> (leftX, topY)
      const d1 = distToSegment(x, y, leftX, baseY, leftX, topY);
      // S2: Left arch (leftX, topY) -> (leftX + archRx, archTop) -> (leftX + archRx*2, topY)
      const d2 = distToArc(x, y, leftX + 20 * scale, topY, 20 * scale, Math.PI, Math.PI * 2);
      // S3: Left inner diagonal (leftX + 40*scale, topY) -> (midX, midY)
      const d3 = distToSegment(x, y, leftX + 40 * scale, topY, midX, midY);
      // S4: Right inner diagonal (midX, midY) -> (rightX - 40*scale, topY)
      const d4 = distToSegment(x, y, midX, midY, rightX - 40 * scale, topY);
      // S5: Right arch (rightX - 40*scale, topY) -> (rightX, topY)
      const d5 = distToArc(x, y, rightX - 20 * scale, topY, 20 * scale, Math.PI, Math.PI * 2);
      // S6: Right vertical stem (rightX, topY) -> (rightX, baseY)
      const d6 = distToSegment(x, y, rightX, topY, rightX, baseY);

      const mDist = Math.min(d1, d2, d3, d4, d5, d6);

      // Ambient Drop Shadow behind the 'M'
      const shadowDy = 6 * scale;
      const shadowDist = Math.hypot(x - midX, y - (baseY - 40 * scale + shadowDy)) / (W * 0.35);
      if (mDist > strokeR && mDist < strokeR + 18 * scale) {
        const shadowAmt = Math.pow(1.0 - (mDist - strokeR) / (18 * scale), 1.8) * 0.35;
        // Cyan-tinted glow shadow
        pr = Math.round(pr + (TEAL_MID[0] - pr) * shadowAmt * 0.4);
        pg = Math.round(pg + (TEAL_MID[1] - pg) * shadowAmt * 0.4);
        pb = Math.round(pb + (CYAN_BRIGHT[2] - pb) * shadowAmt * 0.4);
      }

      if (mDist <= strokeR) {
        // Pixel is inside the 'M' ribbon!
        // Calculate gradient based on position along the stroke / horizontal position
        const tX = clamp((x - (leftX - strokeR)) / ((rightX + strokeR) - (leftX - strokeR)), 0, 1);
        const tY = clamp((y - archTop) / (baseY - archTop), 0, 1);

        // Multi-stop gradient
        let mc = tX < 0.5
          ? lerp(TEAL_DEEP, TEAL_MID, tX * 2)
          : lerp(TEAL_MID, SKY_LIGHT, (tX - 0.5) * 2);

        // Subtle vertical highlight on top curves
        const topHighlight = (1.0 - tY) * 0.15;
        mc = lerp(mc, WHITE, topHighlight);

        // Inner cylindrical shading for 3D depth
        const distFromCenterline = mDist / strokeR;
        const innerBevel = Math.pow(1.0 - distFromCenterline, 0.7);
        mc = lerp(mc, WHITE, (1.0 - distFromCenterline) * 0.12);

        pr = mc[0]; pg = mc[1]; pb = mc[2];
      }

      put(x, y, pr, pg, pb, pa);
    }
  }

  // 8. Box-downsample S×S to target size with alpha coverage
  const out = new Uint8Array(size * size * 4);
  for (let y = 0; y < size; y++) {
    for (let x = 0; x < size; x++) {
      let r = 0, g = 0, b = 0, a = 0;
      for (let sy = 0; sy < S; sy++) {
        for (let sx = 0; sx < S; sx++) {
          const px = x * S + sx, py = y * S + sy;
          const i = (py * W + px) * 4;
          r += buf[i]; g += buf[i + 1]; b += buf[i + 2]; a += buf[i + 3];
        }
      }
      const n = S * S, o = (y * size + x) * 4;
      out[o]     = Math.round(r / n);
      out[o + 1] = Math.round(g / n);
      out[o + 2] = Math.round(b / n);
      out[o + 3] = Math.round(a / n);
    }
  }
  return out;
}

/** Minimal PNG encoder (RGBA, non-interlaced) */
function png(rgba, size) {
  const raw = Buffer.alloc((size * 4 + 1) * size);
  for (let y = 0; y < size; y++) {
    raw[y * (size * 4 + 1)] = 0; // filter: none
    Buffer.from(rgba.buffer, y * size * 4, size * 4)
      .copy(raw, y * (size * 4 + 1) + 1);
  }
  const crcTable = (() => {
    const t = new Int32Array(256);
    for (let n = 0; n < 256; n++) { let c = n;
      for (let k = 0; k < 8; k++) c = c & 1 ? 0xedb88320 ^ (c >>> 1) : c >>> 1;
      t[n] = c; }
    return t;
  })();
  const crc = buf => { let c = -1;
    for (const b of buf) c = crcTable[(c ^ b) & 0xff] ^ (c >>> 8);
    return (c ^ -1) >>> 0; };
  const chunk = (type, data) => {
    const len = Buffer.alloc(4); len.writeUInt32BE(data.length);
    const td = Buffer.concat([Buffer.from(type, "ascii"), data]);
    const cr = Buffer.alloc(4); cr.writeUInt32BE(crc(td));
    return Buffer.concat([len, td, cr]);
  };
  const ihdr = Buffer.alloc(13);
  ihdr.writeUInt32BE(size, 0); ihdr.writeUInt32BE(size, 4);
  ihdr[8] = 8; ihdr[9] = 6; ihdr[10] = 0; ihdr[11] = 0; ihdr[12] = 0; // 8-bit RGBA
  return Buffer.concat([
    Buffer.from([0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a]),
    chunk("IHDR", ihdr),
    chunk("IDAT", deflateSync(raw, { level: 9 })),
    chunk("IEND", Buffer.alloc(0)),
  ]);
}

/** Vector SVG representation with dark/light mode and modern standards */
const MODERN_SVG = `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 512 512" width="100%" height="100%">
  <defs>
    <!-- Background Gradient -->
    <linearGradient id="bgGrad" x1="0%" y1="0%" x2="100%" y2="100%">
      <stop offset="0%" stop-color="#0e1524"/>
      <stop offset="50%" stop-color="#0a0d14"/>
      <stop offset="100%" stop-color="#04060a"/>
    </linearGradient>

    <!-- Radial Ambient Center Bloom -->
    <radialGradient id="centerGlow" cx="50%" cy="46%" r="58%">
      <stop offset="0%" stop-color="#2dd4bf" stop-opacity="0.25"/>
      <stop offset="50%" stop-color="#06b6d4" stop-opacity="0.08"/>
      <stop offset="100%" stop-color="#0a0c10" stop-opacity="0"/>
    </radialGradient>

    <!-- Glassmorphic Specular Highlight -->
    <linearGradient id="specular" x1="0%" y1="0%" x2="70%" y2="70%">
      <stop offset="0%" stop-color="#ffffff" stop-opacity="0.12"/>
      <stop offset="35%" stop-color="#ffffff" stop-opacity="0.02"/>
      <stop offset="100%" stop-color="#ffffff" stop-opacity="0"/>
    </linearGradient>

    <!-- Primary 'M' Ribbon Gradient: Electric Teal to Bright Cyan to Sky Blue -->
    <linearGradient id="mGrad" x1="0%" y1="100%" x2="100%" y2="0%">
      <stop offset="0%" stop-color="#0d9488"/>
      <stop offset="25%" stop-color="#14b8a6"/>
      <stop offset="55%" stop-color="#2dd4bf"/>
      <stop offset="80%" stop-color="#22d3ee"/>
      <stop offset="100%" stop-color="#38bdf8"/>
    </linearGradient>

    <!-- Beacon Radial Glow -->
    <radialGradient id="beaconGlow" cx="50%" cy="50%" r="50%">
      <stop offset="0%" stop-color="#ffffff"/>
      <stop offset="35%" stop-color="#67e8f9"/>
      <stop offset="70%" stop-color="#2dd4bf"/>
      <stop offset="100%" stop-color="#06b6d4" stop-opacity="0"/>
    </radialGradient>

    <!-- Glassmorphic Rim -->
    <linearGradient id="borderGrad" x1="0%" y1="0%" x2="100%" y2="100%">
      <stop offset="0%" stop-color="#ffffff" stop-opacity="0.22"/>
      <stop offset="40%" stop-color="#38bdf8" stop-opacity="0.14"/>
      <stop offset="100%" stop-color="#ffffff" stop-opacity="0.03"/>
    </linearGradient>

    <!-- Subtle Drop Glow -->
    <filter id="dropGlow" x="-20%" y="-20%" width="140%" height="140%">
      <feDropShadow dx="0" dy="10" stdDeviation="16" flood-color="#06b6d4" flood-opacity="0.38"/>
      <feDropShadow dx="0" dy="2" stdDeviation="4" flood-color="#000000" flood-opacity="0.5"/>
    </filter>
  </defs>

  <!-- Squircle Base (23.5% Continuous Corner Radius) -->
  <rect x="20" y="20" width="472" height="472" rx="114" ry="114" fill="url(#bgGrad)"/>
  <rect x="20" y="20" width="472" height="472" rx="114" ry="114" fill="url(#centerGlow)"/>
  <rect x="20" y="20" width="472" height="472" rx="114" ry="114" fill="url(#specular)"/>
  <rect x="20" y="20" width="472" height="472" rx="114" ry="114" fill="none" stroke="url(#borderGrad)" stroke-width="2.5"/>

  <!-- Iconic Central Emblem Group -->
  <g filter="url(#dropGlow)">
    <!-- Radar Pulse Arc -->
    <path d="M 200 178 A 66 66 0 0 1 312 178" fill="none" stroke="url(#mGrad)" stroke-width="6.5" stroke-linecap="round" opacity="0.55"/>

    <!-- Luminous Live Pulse Beacon (The "Glance" Focus) -->
    <circle cx="256" cy="154" r="16" fill="url(#beaconGlow)"/>
    <circle cx="256" cy="154" r="6" fill="#ffffff"/>

    <!-- The Modern Continuous Geometric 'M' Ribbon -->
    <path d="M 140 350 L 140 216 C 140 194 158 176 180 176 C 192 176 203 182 210 192 L 256 264 L 302 192 C 309 182 320 176 332 176 C 354 176 372 194 372 216 L 372 350"
          fill="none" stroke="url(#mGrad)" stroke-width="44" stroke-linecap="round" stroke-linejoin="round"/>
  </g>
</svg>`;

// Write output files
mkdirSync(new URL("../public/icons/", import.meta.url), { recursive: true });

// 1. Write vector SVGs
writeFileSync(new URL("../public/icons/icon.svg", import.meta.url), MODERN_SVG);
writeFileSync(new URL("../public/favicon.svg", import.meta.url), MODERN_SVG);
console.log("wrote public/icons/icon.svg");
console.log("wrote public/favicon.svg");

// 2. Generate PNGs across all target resolutions
const targets = [
  { size: 512, file: "icon-512.png" },
  { size: 192, file: "icon-192.png" },
  { size: 180, file: "apple-touch-icon.png" },
  { size: 32,  file: "favicon-32.png" },
];

for (const { size, file } of targets) {
  const data = png(render(size), size);
  writeFileSync(new URL(`../public/icons/${file}`, import.meta.url), data);
  console.log(`wrote public/icons/${file} (${size}x${size}) ${(data.length / 1024).toFixed(1)} KB`);
}
