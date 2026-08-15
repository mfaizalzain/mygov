// tools/make-icons.mjs
// Generates state-of-the-art PWA icons (PNGs and SVGs) for Malaysia at a Glance (mygov).
// Master Motif: Sovereign Ruby & Gold Bunga Raya (Option BR-2)
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
    { size: 32,  file: "favicon-32.png" },
  ];

  console.log("Generating high-DPI PWA PNG suite...");
  for (const { size, file } of targets) {
    const dest = new URL(`../public/icons/${file}`, import.meta.url).pathname;
    execSync(`sips -z ${size} ${size} "${srcMaster}" --out "${dest}" 2>/dev/null`);
    console.log(`wrote public/icons/${file} (${size}x${size})`);
  }

  // 2. Generate master vector SVGs with embedded high-DPI master artwork
  const png512 = readFileSync(new URL("../public/icons/icon-512.png", import.meta.url));
  const b64 = png512.toString("base64");
  const svgContent = `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 512 512" width="100%" height="100%">
  <!-- Sovereign Ruby & Gold Bunga Raya (National Flower) -->
  <image width="512" height="512" href="data:image/png;base64,${b64}"/>
</svg>
`;

  writeFileSync(new URL("../public/icons/icon.svg", import.meta.url), svgContent);
  writeFileSync(new URL("../public/favicon.svg", import.meta.url), svgContent);
  console.log("wrote public/icons/icon.svg");
  console.log("wrote public/favicon.svg");
} else {
  console.error("tools/master_bunga_raya.png not found!");
}
