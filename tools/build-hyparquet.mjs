#!/usr/bin/env node
/**
 * Rebuild public/vendor/hyparquet.min.js.
 *
 * The MoH KKMNOW health datasets ship as Parquet, so the page needs a Parquet
 * reader. Two constraints shape this bundle:
 *
 *   1. The CSP allows scripts from 'self' only, and the app deliberately has no
 *      build step, so the reader has to be vendored as one ready-made file with
 *      a subresource-integrity hash — exactly like Chart.js and Leaflet.
 *   2. Every KKMNOW file is BROTLI-compressed. hyparquet core handles snappy
 *      and gzip only, and no browser exposes brotli to script
 *      (DecompressionStream is gzip/deflate). So one decompressor is pulled in
 *      from hyparquet-compressors — just BROTLI, not the zstd/lz4/snappy wasm
 *      the full package would drag along.
 *
 * Run:  node tools/build-hyparquet.mjs
 * Then paste the printed integrity hash into the <script> tag in index.html.
 */
import { mkdtemp, rm, writeFile, readFile, mkdir } from "node:fs/promises";
import { createHash } from "node:crypto";
import { execFileSync } from "node:child_process";
import { tmpdir } from "node:os";
import { join, dirname } from "node:path";
import { fileURLToPath } from "node:url";

const HYPARQUET = "1.28.1";      // pinned: a bundle is only reproducible if its inputs are
const COMPRESSORS = "1.1.1";
const ESBUILD = "0.25.10";

const root = join(dirname(fileURLToPath(import.meta.url)), "..");
const out = join(root, "public", "vendor", "hyparquet.min.js");

const tar = async (pkg, version, into) => {
  const url = `https://registry.npmjs.org/${pkg}/-/${pkg}-${version}.tgz`;
  const res = await fetch(url);
  if (!res.ok) throw new Error(`${url} → HTTP ${res.status}`);
  const tgz = join(into, `${pkg}.tgz`);
  await writeFile(tgz, Buffer.from(await res.arrayBuffer()));
  const dir = join(into, pkg);
  await mkdir(dir, { recursive: true });
  execFileSync("tar", ["xzf", tgz, "-C", dir, "--strip-components=1"]);
  return dir;
};

const work = await mkdtemp(join(tmpdir(), "hyparquet-"));
try {
  await tar("hyparquet", HYPARQUET, work);
  await tar("hyparquet-compressors", COMPRESSORS, work);
  const entry = join(work, "entry.js");
  await writeFile(entry, `
import { parquetReadObjects } from './hyparquet/src/index.js'
import { decompressBrotli } from './hyparquet-compressors/src/brotli.js'
export { parquetReadObjects }
export const compressors = { BROTLI: decompressBrotli }
`);
  execFileSync("npx", ["--yes", `esbuild@${ESBUILD}`, entry, "--bundle", "--minify",
    "--format=iife", "--global-name=hyparquet", "--target=es2022",
    "--legal-comments=none", `--outfile=${out}`], { stdio: "inherit" });

  const bytes = await readFile(out);
  const sri = "sha384-" + createHash("sha384").update(bytes).digest("base64");
  console.log(`\n${out}\n${(bytes.length / 1024).toFixed(1)} kB\nintegrity="${sri}"`);
} finally {
  await rm(work, { recursive: true, force: true });
}
