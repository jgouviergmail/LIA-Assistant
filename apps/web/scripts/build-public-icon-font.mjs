#!/usr/bin/env node
/**
 * Write the public pages' icon font: Material Symbols Outlined, cut down to the
 * icons those pages draw.
 *
 * The application loads the full variable font from Google Fonts, because the
 * cards the model writes may name any icon. That file is 4 MB (four axes, every
 * icon), and the landing downloaded it before the reader scrolled — for the five
 * icons of its demo (measured 2026-10-28). Public pages (`.landing-page`) now
 * draw their icons from this subset, self-hosted through `next/font/local`
 * (`lib/fonts.ts`), so the full font is never requested there.
 *
 * Input: `src/fonts/material-symbols-public/manifest.json` — `icons`, edited by
 * hand when the guard names a missing one, and `axes`, the ranges the icon
 * rules of `styles/lia-components.css` actually set (`wght` 400, `GRAD` 0,
 * `FILL` 0-1, `opsz` 20 or 24). The script asks Google Fonts for exactly that
 * cut (`icon_names=`), writes the woff2 beside the manifest, and records the
 * request and the file's SHA-256 there. The guard
 * `src/lib/__tests__/public-icon-font.guard.test.ts` refuses an icon a public
 * page draws that the manifest lacks, and a font that is not the one recorded.
 *
 * Run by hand (network); the build never fetches anything.
 *
 * Usage (from the repository root):
 *     node apps/web/scripts/build-public-icon-font.mjs
 */
import { createHash } from 'node:crypto';
import { readFileSync, writeFileSync } from 'node:fs';
import { join, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

import { formatJson } from './format-json.mjs';

const here = fileURLToPath(new URL('.', import.meta.url));
const fontDir = resolve(here, '..', 'src', 'fonts', 'material-symbols-public');
const manifestPath = join(fontDir, 'manifest.json');
const fontFile = 'material-symbols-public.woff2';

// Google Fonts serves woff2 to the user agents that support it, and a CSS of
// TrueType URLs to anything it does not recognise.
const USER_AGENT =
  'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 ' +
  '(KHTML, like Gecko) Chrome/141.0.0.0 Safari/537.36';

const manifest = JSON.parse(readFileSync(manifestPath, 'utf8'));
const icons = [...new Set(manifest.icons)].sort();
const cssUrl =
  'https://fonts.googleapis.com/css2?family=Material+Symbols+Outlined:' +
  `${manifest.axes}&icon_names=${icons.join(',')}&display=block`;

async function fetchOk(url) {
  const response = await fetch(url, { headers: { 'User-Agent': USER_AGENT } });
  if (!response.ok) throw new Error(`${response.status} ${response.statusText} for ${url}`);
  return response;
}

const css = await (await fetchOk(cssUrl)).text();
const match = css.match(/src:\s*url\((https:\/\/fonts\.gstatic\.com\/[^)]+)\)\s*format\('woff2'\)/);
if (!match) throw new Error(`no woff2 source in the stylesheet:\n${css}`);
const bytes = Buffer.from(await (await fetchOk(match[1])).arrayBuffer());
writeFileSync(join(fontDir, fontFile), bytes);

const written = {
  axes: manifest.axes,
  icons,
  source: cssUrl,
  file: fontFile,
  sha256: createHash('sha256').update(bytes).digest('hex'),
};
writeFileSync(manifestPath, formatJson(written));
console.log(`${fontFile}: ${icons.length} icons, ${bytes.length} bytes`);
