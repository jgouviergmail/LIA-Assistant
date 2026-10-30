#!/usr/bin/env node
/**
 * Write the landing captures' static variants from their originals.
 *
 * For every view `src/lib/landing/captures.ts` declares, reads the original
 * under `public/` and writes `public/screenshots/variants/<file>-<width>.webp`
 * for every width `CAPTURE_VARIANT_WIDTHS` lists — never enlarged — then
 * records in `variants/manifest.json` the SHA-256 of the original each set was
 * written from. Variants no view names any more are removed. The guard
 * `src/lib/landing/__tests__/captures.guard.test.ts` compares those hashes with
 * the originals, so a capture campaign that replaces a file without running
 * this script fails CI instead of shipping a stale picture.
 *
 * Why files rather than the image optimizer: ADR-330 — on the production host
 * the optimizer decodes the original per variant per cache expiry, and its
 * responses carry no extension, so the CDN never caches them.
 *
 * sharp is the encoder Next itself ships, resolved from there as
 * `build-article-images.mjs` does. WebP 82 / effort 6, the article setting:
 * compared at 1:1 on a 1600-px capture (2026-10-28), the interface text is
 * indistinguishable from the PNG at a tenth of its weight.
 *
 * The views come from `captures.ts` itself, loaded through Node's type
 * stripping (Node 22.18+), so the script cannot write names the page does not
 * read.
 *
 * Usage (from the repository root):
 *     node apps/web/scripts/build-capture-variants.mjs
 */
import { createHash } from 'node:crypto';
import { mkdirSync, readdirSync, readFileSync, rmSync, writeFileSync } from 'node:fs';
import { createRequire } from 'node:module';
import { dirname, join, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

import {
  allCaptureViews,
  captureOriginalPath,
  captureVariantPath,
  CAPTURE_VARIANT_WIDTHS,
  CAPTURE_VARIANTS_DIRECTORY,
  CAPTURE_VARIANTS_MANIFEST,
} from '../src/lib/landing/captures.ts';
import { formatJson } from './format-json.mjs';

const require = createRequire(import.meta.url);
const sharp = require(
  require.resolve('sharp', { paths: [dirname(require.resolve('next/package.json'))] })
);

const WEBP = { quality: 82, effort: 6 };

const here = fileURLToPath(new URL('.', import.meta.url));
const publicDir = resolve(here, '..', 'public');
const onDisk = publicPath => join(publicDir, ...publicPath.split('/').filter(Boolean));

const variantsDir = onDisk(CAPTURE_VARIANTS_DIRECTORY);
mkdirSync(variantsDir, { recursive: true });

const sources = {};
const expected = new Set(['manifest.json']);
for (const view of allCaptureViews()) {
  const original = captureOriginalPath(view);
  const bytes = readFileSync(onDisk(original));
  const image = sharp(bytes, { limitInputPixels: false });
  for (const width of CAPTURE_VARIANT_WIDTHS) {
    const variant = captureVariantPath(view.file, width);
    await image
      .clone()
      .resize({ width, withoutEnlargement: true })
      .webp(WEBP)
      .toFile(onDisk(variant));
    expected.add(variant.split('/').pop());
  }
  sources[view.file] = { original, sha256: createHash('sha256').update(bytes).digest('hex') };
  console.log(`${view.file}: ${CAPTURE_VARIANT_WIDTHS.length} webp`);
}

const removed = readdirSync(variantsDir).filter(name => !expected.has(name));
for (const name of removed) rmSync(join(variantsDir, name));

const manifest = {
  generator: 'apps/web/scripts/build-capture-variants.mjs',
  widths: [...CAPTURE_VARIANT_WIDTHS],
  webp: WEBP,
  sources,
};
writeFileSync(onDisk(CAPTURE_VARIANTS_MANIFEST), formatJson(manifest));
console.log(
  `${Object.keys(sources).length} captures, ${expected.size - 1} variants written to ${variantsDir}` +
    (removed.length ? `, ${removed.length} orphan(s) removed` : '')
);
