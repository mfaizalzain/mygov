// Generates the PWA icons as real PNGs with zero dependencies.
// Draws at 4x then box-downsamples, which gives clean anti-aliased edges.
// Run: node tools/make-icons.mjs
import { deflateSync } from "node:zlib";
import { writeFileSync, mkdirSync } from "node:fs";

const BG   = [10, 12, 16];      // near-black slate, matches --bg
const CARD = [21, 25, 33];      // subtle inner panel
const TEAL = [45, 212, 191];    // accent
const TEAL2= [34, 211, 238];    // accent secondary (gradient end)

const lerp = (a, b, t) => a.map((v, i) => Math.round(v + (b[i] - v) * t));

/** Signed-distance helper for a rounded rectangle. */
function insideRoundRect(x, y, w, h, r) {
  const dx = Math.max(Math.abs(x - w / 2) - (w / 2 - r), 0);
  const dy = Math.max(Math.abs(y - h / 2) - (h / 2 - r), 0);
  return Math.hypot(dx, dy) <= r;
}

function render(size) {
  const S = 4, W = size * S;                    // supersample
  const buf = new Uint8Array(W * W * 3);

  const put = (x, y, c) => { const i = (y * W + x) * 3;
    buf[i] = c[0]; buf[i + 1] = c[1]; buf[i + 2] = c[2]; };

  const radius = W * 0.22;                      // rounded-square app icon
  // three ascending bars = "data dashboard", with a rising spark line above
  const bars = [
    { x: 0.24, h: 0.26 },
    { x: 0.435, h: 0.42 },
    { x: 0.63, h: 0.58 },
  ];
  const barW = W * 0.13, barR = barW * 0.36;
  const baseY = W * 0.76;

  for (let y = 0; y < W; y++) {
    for (let x = 0; x < W; x++) {
      if (!insideRoundRect(x, y, W, W, radius)) { put(x, y, [0, 0, 0]); continue; }
      // vertical background gradient
      let c = lerp(BG, CARD, y / W);

      for (let b = 0; b < bars.length; b++) {
        const bx = W * bars[b].x, bh = W * bars[b].h;
        const by = baseY - bh;
        const lx = x - bx, ly = y - by;
        if (lx >= 0 && lx <= barW && ly >= 0 && ly <= bh) {
          // round the bar's corners
          const rr = Math.min(barR, bh / 2);
          const cx = Math.min(Math.max(lx, rr), barW - rr);
          const cy = Math.min(Math.max(ly, rr), bh - rr);
          if (Math.hypot(lx - cx, ly - cy) <= rr) {
            c = lerp(TEAL2, TEAL, b / (bars.length - 1));
            // subtle vertical shading inside each bar
            c = lerp(c, [255, 255, 255], 0.10 * (1 - ly / bh));
          }
        }
      }
      put(x, y, c);
    }
  }

  // Box-downsample to the target size, compositing against transparency
  // outside the rounded square (alpha from coverage).
  const out = new Uint8Array(size * size * 4);
  for (let y = 0; y < size; y++) {
    for (let x = 0; x < size; x++) {
      let r = 0, g = 0, b = 0, cov = 0;
      for (let sy = 0; sy < S; sy++) {
        for (let sx = 0; sx < S; sx++) {
          const px = x * S + sx, py = y * S + sy;
          const inside = insideRoundRect(px, py, W, W, W * 0.22);
          if (inside) {
            const i = (py * W + px) * 3;
            r += buf[i]; g += buf[i + 1]; b += buf[i + 2]; cov++;
          }
        }
      }
      const n = S * S, o = (y * size + x) * 4;
      if (cov === 0) { out[o] = out[o+1] = out[o+2] = out[o+3] = 0; continue; }
      out[o]     = Math.round(r / cov);
      out[o + 1] = Math.round(g / cov);
      out[o + 2] = Math.round(b / cov);
      out[o + 3] = Math.round((cov / n) * 255);
    }
  }
  return out;
}

/** Minimal PNG encoder (RGBA, non-interlaced). */
function png(rgba, size) {
  const raw = Buffer.alloc((size * 4 + 1) * size);
  for (let y = 0; y < size; y++) {
    raw[y * (size * 4 + 1)] = 0;                       // filter: none
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
  ihdr[8] = 8; ihdr[9] = 6; ihdr[10] = 0; ihdr[11] = 0; ihdr[12] = 0;  // 8-bit RGBA
  return Buffer.concat([
    Buffer.from([0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a]),
    chunk("IHDR", ihdr),
    chunk("IDAT", deflateSync(raw, { level: 9 })),
    chunk("IEND", Buffer.alloc(0)),
  ]);
}

mkdirSync(new URL("../public/icons/", import.meta.url), { recursive: true });
for (const size of [192, 512, 180]) {
  const file = size === 180 ? "apple-touch-icon.png" : `icon-${size}.png`;
  const data = png(render(size), size);
  writeFileSync(new URL(`../public/icons/${file}`, import.meta.url), data);
  console.log(`wrote public/icons/${file}  ${(data.length / 1024).toFixed(1)} KB`);
}
