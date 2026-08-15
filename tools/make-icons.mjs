// tools/make-icons.mjs
// Generates state-of-the-art PWA icons (PNGs, SVGs, ICO) for Malaysia at a Glance (mygov).
// Master Motif: Sovereign Ruby & Gold Bunga Raya (Option BR-2) - 100% Transparent Background
// Run: node tools/make-icons.mjs

import { writeFileSync, mkdirSync, existsSync, readFileSync } from "node:fs";
import { execSync } from "node:child_process";

mkdirSync(new URL("../public/icons/", import.meta.url), { recursive: true });

const srcMaster = new URL("./master_bunga_raya.png", import.meta.url).pathname;

if (existsSync(srcMaster)) {
  // 1. Generate PNGs across all target resolutions
  const targets = [
    { size: 512, file: "icon-512.png" },
    { size: 192, file: "icon-192.png" },
    { size: 180, file: "apple-touch-icon.png" },
    { size: 48,  file: "favicon-48.png" },
    { size: 32,  file: "favicon-32.png" },
    { size: 16,  file: "favicon-16.png" },
  ];

  console.log("Generating 100% transparent high-DPI PWA PNG suite...");
  for (const { size, file } of targets) {
    const dest = new URL(`../public/icons/${file}`, import.meta.url).pathname;
    execSync(`sips -z ${size} ${size} "${srcMaster}" --out "${dest}" 2>/dev/null`);
    console.log(`wrote public/icons/${file} (${size}x${size})`);
  }

  // 2. Generate multi-resolution ICO file (16x16, 32x32, 48x48)
  const buf16 = readFileSync(new URL("../public/icons/favicon-16.png", import.meta.url));
  const buf32 = readFileSync(new URL("../public/icons/favicon-32.png", import.meta.url));
  const buf48 = readFileSync(new URL("../public/icons/favicon-48.png", import.meta.url));
  const images = [
    { w: 16, h: 16, buf: buf16 },
    { w: 32, h: 32, buf: buf32 },
    { w: 48, h: 48, buf: buf48 },
  ];

  const header = Buffer.alloc(6);
  header.writeUInt16LE(0, 0);
  header.writeUInt16LE(1, 2);
  header.writeUInt16LE(images.length, 4);

  let offset = 6 + 16 * images.length;
  const entries = [];
  for (const img of images) {
    const entry = Buffer.alloc(16);
    entry.writeUInt8(img.w, 0);
    entry.writeUInt8(img.h, 1);
    entry.writeUInt8(0, 2);
    entry.writeUInt8(0, 3);
    entry.writeUInt16LE(1, 4);
    entry.writeUInt16LE(32, 6);
    entry.writeUInt32LE(img.buf.length, 8);
    entry.writeUInt32LE(offset, 12);
    entries.push(entry);
    offset += img.buf.length;
  }

  const icoBuffer = Buffer.concat([header, ...entries, ...images.map(img => img.buf)]);
  writeFileSync(new URL("../public/favicon.ico", import.meta.url), icoBuffer);
  console.log(`wrote public/favicon.ico (${(icoBuffer.length / 1024).toFixed(1)} KB)`);

  // 3. Generate master vector SVGs with embedded high-DPI master artwork
  const png128 = readFileSync(new URL("../public/icons/icon-192.png", import.meta.url));
  const b64 = png128.toString("base64");
  const svgContent = `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 192 192" width="100%" height="100%">
  <!-- Sovereign Ruby & Gold Bunga Raya (National Flower) - 100% Transparent Background -->
  <image width="192" height="192" href="data:image/png;base64,${b64}"/>
</svg>
`;

  writeFileSync(new URL("../public/icons/icon.svg", import.meta.url), svgContent);
  writeFileSync(new URL("../public/favicon.svg", import.meta.url), svgContent);
  console.log("wrote public/icons/icon.svg");
  console.log("wrote public/favicon.svg");
} else {
  console.error("tools/master_bunga_raya.png not found!");
}
