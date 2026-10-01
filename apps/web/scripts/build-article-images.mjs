#!/usr/bin/env node
/**
 * Write the blog illustrations' static variants from their masters (ADR-330).
 *
 * For every `<slug>.png` in the masters directory (an argument — the masters
 * are not versioned: the 28 shipped before this script live in git history,
 * `git show <commit>:apps/web/public/articles/<slug>.png`), writes into
 * `public/articles/`:
 *   - `<slug>-<width>.webp` for every width `ARTICLE_IMAGE_WIDTHS` declares;
 *   - `<slug>-og.jpg`, the 16:9 social image at `ARTICLE_SOCIAL_IMAGE`.
 *
 * Why files rather than the image optimizer: on the production host the
 * optimizer decoded a 7-MB RGBA PNG per variant per cache expiry, and its
 * responses carry no extension, so the CDN never cached them (measured
 * 2026-10-01). A file is encoded once, here, and cached by extension at the
 * edge.
 *
 * sharp is the encoder Next itself ships; the quality values were chosen on
 * the dithered, flat-colour masters (WebP 82 / effort 6 keeps the dots crisp
 * at a third of the lossless size; JPEG 82 mozjpeg for the card previews X
 * and LinkedIn fetch — X refuses images above 5 MB).
 *
 * Usage (from the repository root):
 *     node apps/web/scripts/build-article-images.mjs exports/articles-masters [slug ...]
 */
import { mkdirSync, readdirSync } from 'node:fs';
import { createRequire } from 'node:module';
import { basename, dirname, join, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

// sharp is not a dependency of the app: it is the encoder Next itself ships
// (an optional dependency of `next`), resolved from there on purpose so this
// script and the framework encode with the same library — declaring it would
// pin a second copy for a script run by hand.
const require = createRequire(import.meta.url);
const sharp = require(
  require.resolve('sharp', { paths: [dirname(require.resolve('next/package.json'))] })
);

const WIDTHS = [480, 768, 1024, 1536];
const SOCIAL = { width: 1200, height: 675 };
const WEBP = { quality: 82, effort: 6 };
const JPEG = { quality: 82, mozjpeg: true };

const here = fileURLToPath(new URL('.', import.meta.url));
const outDir = resolve(here, '..', 'public', 'articles');

const [mastersArg, ...only] = process.argv.slice(2);
if (!mastersArg) {
  console.error('usage: build-article-images.mjs <masters dir> [slug ...]');
  process.exit(2);
}
const mastersDir = resolve(mastersArg);
mkdirSync(outDir, { recursive: true });

const masters = readdirSync(mastersDir)
  .filter(name => name.endsWith('.png'))
  .map(name => basename(name, '.png'))
  .filter(slug => only.length === 0 || only.includes(slug))
  .sort();

if (masters.length === 0) {
  console.error(`no master found in ${mastersDir}`);
  process.exit(1);
}

let written = 0;
for (const slug of masters) {
  const master = join(mastersDir, `${slug}.png`);
  const image = sharp(master, { limitInputPixels: false });
  for (const width of WIDTHS) {
    await image
      .clone()
      .resize({ width, withoutEnlargement: true })
      .webp(WEBP)
      .toFile(join(outDir, `${slug}-${width}.webp`));
    written += 1;
  }
  await image
    .clone()
    .resize(SOCIAL.width, SOCIAL.height, { fit: 'cover', position: 'centre' })
    .flatten({ background: '#ffffff' })
    .jpeg(JPEG)
    .toFile(join(outDir, `${slug}-og.jpg`));
  written += 1;
  console.log(`${slug}: ${WIDTHS.length} webp + og.jpg`);
}
console.log(`${written} files written to ${outDir}`);
