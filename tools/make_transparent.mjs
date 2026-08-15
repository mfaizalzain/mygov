import { readFileSync, writeFileSync } from "fs";
import { inflateSync, deflateSync } from "zlib";

function decodePNG(buffer) {
  let offset = 8;
  let width = 0, height = 0, bitDepth = 0, colorType = 0;
  const idatChunks = [];

  while (offset < buffer.length) {
    const length = buffer.readUInt32BE(offset);
    const type = buffer.toString("ascii", offset + 4, offset + 8);
    const data = buffer.slice(offset + 8, offset + 8 + length);
    offset += 12 + length;

    if (type === "IHDR") {
      width = data.readUInt32BE(0);
      height = data.readUInt32BE(4);
      bitDepth = data[8];
      colorType = data[9];
    } else if (type === "IDAT") {
      idatChunks.push(data);
    } else if (type === "IEND") {
      break;
    }
  }

  const decompressed = inflateSync(Buffer.concat(idatChunks));
  const bytesPerPixel = colorType === 6 ? 4 : colorType === 2 ? 3 : 1;
  const rgba = new Uint8Array(width * height * 4);
  const scanlineLength = width * bytesPerPixel;
  
  let srcOffset = 0;
  const prevRow = new Uint8Array(scanlineLength);
  const curRow = new Uint8Array(scanlineLength);

  for (let y = 0; y < height; y++) {
    const filterType = decompressed[srcOffset++];
    for (let x = 0; x < scanlineLength; x++) {
      let val = decompressed[srcOffset++];
      const a = x >= bytesPerPixel ? curRow[x - bytesPerPixel] : 0;
      const b = prevRow[x];
      const c = x >= bytesPerPixel ? prevRow[x - bytesPerPixel] : 0;

      if (filterType === 1) val = (val + a) & 0xff;
      else if (filterType === 2) val = (val + b) & 0xff;
      else if (filterType === 3) val = (val + Math.floor((a + b) / 2)) & 0xff;
      else if (filterType === 4) {
        const p = a + b - c;
        const pa = Math.abs(p - a), pb = Math.abs(p - b), pc = Math.abs(p - c);
        const pr = pa <= pb && pa <= pc ? a : pb <= pc ? b : c;
        val = (val + pr) & 0xff;
      }
      curRow[x] = val;
    }

    for (let x = 0; x < width; x++) {
      const dstIdx = (y * width + x) * 4;
      if (colorType === 6) {
        const srcIdx = x * 4;
        rgba[dstIdx] = curRow[srcIdx];
        rgba[dstIdx + 1] = curRow[srcIdx + 1];
        rgba[dstIdx + 2] = curRow[srcIdx + 2];
        rgba[dstIdx + 3] = curRow[srcIdx + 3];
      } else if (colorType === 2) {
        const srcIdx = x * 3;
        rgba[dstIdx] = curRow[srcIdx];
        rgba[dstIdx + 1] = curRow[srcIdx + 1];
        rgba[dstIdx + 2] = curRow[srcIdx + 2];
        rgba[dstIdx + 3] = 255;
      }
    }
    prevRow.set(curRow);
  }

  return { width, height, rgba };
}

function encodePNG(rgba, width, height) {
  const raw = Buffer.alloc((width * 4 + 1) * height);
  for (let y = 0; y < height; y++) {
    raw[y * (width * 4 + 1)] = 0;
    Buffer.from(rgba.buffer, y * width * 4, width * 4).copy(raw, y * (width * 4 + 1) + 1);
  }

  const crcTable = (() => {
    const t = new Int32Array(256);
    for (let n = 0; n < 256; n++) {
      let c = n;
      for (let k = 0; k < 8; k++) c = c & 1 ? 0xedb88320 ^ (c >>> 1) : c >>> 1;
      t[n] = c;
    }
    return t;
  })();

  const crc = buf => {
    let c = -1;
    for (const b of buf) c = crcTable[(c ^ b) & 0xff] ^ (c >>> 8);
    return (c ^ -1) >>> 0;
  };

  const chunk = (type, data) => {
    const len = Buffer.alloc(4); len.writeUInt32BE(data.length);
    const td = Buffer.concat([Buffer.from(type, "ascii"), data]);
    const cr = Buffer.alloc(4); cr.writeUInt32BE(crc(td));
    return Buffer.concat([len, td, cr]);
  };

  const ihdr = Buffer.alloc(13);
  ihdr.writeUInt32BE(width, 0);
  ihdr.writeUInt32BE(height, 4);
  ihdr[8] = 8; ihdr[9] = 6; ihdr[10] = 0; ihdr[11] = 0; ihdr[12] = 0;

  return Buffer.concat([
    Buffer.from([0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a]),
    chunk("IHDR", ihdr),
    chunk("IDAT", deflateSync(raw, { level: 9 })),
    chunk("IEND", Buffer.alloc(0)),
  ]);
}

const inputBuf = readFileSync("/Users/faizalzain/Desktop/github-repos/mygov/tools/master_bunga_raya.png");
const { width, height, rgba } = decodePNG(inputBuf);

// Sample background color across top border
let bgSumR = 0, bgSumG = 0, bgSumB = 0, count = 0;
for (let x = 0; x < width; x++) {
  const idx = x * 4;
  bgSumR += rgba[idx];
  bgSumG += rgba[idx + 1];
  bgSumB += rgba[idx + 2];
  count++;
}
const bgR = bgSumR / count;
const bgG = bgSumG / count;
const bgB = bgSumB / count;
console.log(`Average Background Color: RGB(${bgR.toFixed(1)}, ${bgG.toFixed(1)}, ${bgB.toFixed(1)})`);

// Flood fill from all 4 borders
const isBg = new Uint8Array(width * height);
const visited = new Uint8Array(width * height);
const queue = [];

function isBackgroundPixel(idx) {
  const r = rgba[idx], g = rgba[idx + 1], b = rgba[idx + 2];
  // Distance to background color
  const d = Math.hypot(r - bgR, g - bgG, b - bgB);
  // Gold rim is bright (r > 120, g > 90), flower red is (r > 100), background is very dark (r < 45, g < 45, b < 45)
  return d < 40 && (r < 55 && g < 55 && b < 55);
}

for (let x = 0; x < width; x++) {
  queue.push([x, 0], [x, height - 1]);
  visited[x] = 1;
  visited[(height - 1) * width + x] = 1;
}
for (let y = 0; y < height; y++) {
  queue.push([0, y], [width - 1, y]);
  visited[y * width] = 1;
  visited[y * width + (width - 1)] = 1;
}

let head = 0;
while (head < queue.length) {
  const [x, y] = queue[head++];
  const idx = (y * width + x) * 4;
  const pIdx = y * width + x;

  if (isBackgroundPixel(idx)) {
    isBg[pIdx] = 1;
    const neighbors = [[x + 1, y], [x - 1, y], [x, y + 1], [x, y - 1]];
    for (const [nx, ny] of neighbors) {
      if (nx >= 0 && nx < width && ny >= 0 && ny < height) {
        const nIdx = ny * width + nx;
        if (!visited[nIdx]) {
          visited[nIdx] = 1;
          queue.push([nx, ny]);
        }
      }
    }
  }
}

// Write out transparent RGBA
const outRgba = new Uint8Array(width * height * 4);
for (let y = 0; y < height; y++) {
  for (let x = 0; x < width; x++) {
    const idx = (y * width + x) * 4;
    const pIdx = y * width + x;

    if (isBg[pIdx]) {
      outRgba[idx] = 0;
      outRgba[idx + 1] = 0;
      outRgba[idx + 2] = 0;
      outRgba[idx + 3] = 0;
    } else {
      // Edge anti-aliasing calculation
      let bgNeighbors = 0;
      let total = 0;
      for (let dy = -2; dy <= 2; dy++) {
        for (let dx = -2; dx <= 2; dx++) {
          const nx = x + dx, ny = y + dy;
          if (nx >= 0 && nx < width && ny >= 0 && ny < height) {
            total++;
            if (isBg[ny * width + nx]) bgNeighbors++;
          }
        }
      }
      const alpha = 1 - (bgNeighbors / total);
      outRgba[idx] = rgba[idx];
      outRgba[idx + 1] = rgba[idx + 1];
      outRgba[idx + 2] = rgba[idx + 2];
      outRgba[idx + 3] = Math.round(255 * Math.min(Math.max(alpha * 1.35, 0), 1));
    }
  }
}

const outPng = encodePNG(outRgba, width, height);
writeFileSync("/Users/faizalzain/Desktop/github-repos/mygov/tools/master_bunga_raya.png", outPng);
console.log(`Updated tools/master_bunga_raya.png with pure transparent background (${(outPng.length / 1024).toFixed(1)} KB)`);
