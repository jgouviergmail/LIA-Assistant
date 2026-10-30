/**
 * Public pages draw every icon they show from the subset, and the subset is the
 * file its manifest records.
 *
 * `.landing-page .material-symbols-outlined` reads `publicSymbols`
 * (`lib/fonts.ts`), a cut of Material Symbols holding only the icons public
 * pages draw, so the 4 MB variable font is never requested there. The cut has
 * no fallback on purpose. An icon it lacks would show its ligature NAME as
 * text ("check_circle"), and nothing but this guard would see it before a
 * visitor did. Hence three checks:
 *
 * 1. every icon a public page can draw is in the manifest — the icons written
 *    in the six locales' HTML strings (the demo's cards), and those of the two
 *    modules that write an icon span themselves, read from their tables;
 * 2. no other module writes an icon span (the census below), so a new writer
 *    is a decision rather than a missing glyph found in production;
 * 3. the woff2 on disk is the one `scripts/build-public-icon-font.mjs` fetched
 *    for exactly those icons and axes.
 */

import { createHash } from 'node:crypto';
import { readFileSync } from 'node:fs';
import { join } from 'node:path';

import { describe, expect, it } from 'vitest';

import { filesMatching, readSources, SRC_ROOT } from '@/__tests__/source-scan';
import { CARD_ACTION_ICONS } from '@/components/chat/markdown-card-actions';
import { SHOWROOM_DECISION_ICONS } from '@/components/showroom/response-html';
import enDict from '../../../locales/en/translation.json';
import frDict from '../../../locales/fr/translation.json';
import deDict from '../../../locales/de/translation.json';
import esDict from '../../../locales/es/translation.json';
import itDict from '../../../locales/it/translation.json';
import zhDict from '../../../locales/zh/translation.json';

interface FontManifest {
  axes: string;
  icons: string[];
  source: string;
  file: string;
  sha256: string;
}

const FONT_DIR = join(SRC_ROOT, 'fonts', 'material-symbols-public');
const MANIFEST: FontManifest = JSON.parse(readFileSync(join(FONT_DIR, 'manifest.json'), 'utf8'));
const FONT_SHA256 = createHash('sha256')
  .update(readFileSync(join(FONT_DIR, MANIFEST.file)))
  .digest('hex');
const REGENERATE = 'run: node apps/web/scripts/build-public-icon-font.mjs';

/**
 * Every file of `src/` that can carry markup — code, guides, data — tests
 * aside, read at collection. Stylesheets are left out: they style the class,
 * they cannot draw an icon.
 */
const MODULES = readSources(file => /\.(tsx?|mdx?|json|html)$/.test(file.relative) && !file.isTest);

/**
 * Every file whose content (not its comments) names the icon class, and why
 * the icons it draws are covered. A file that starts drawing icons fails here.
 */
const ICON_CLASS_READERS: Record<string, string> = {
  'components/showroom/response-html.ts': 'draws SHOWROOM_DECISION_ICONS, read below',
  'components/chat/markdown-card-actions.tsx': 'draws CARD_ACTION_ICONS, read below',
  'lib/html-markdown.ts': 'drops the icon while converting HTML, draws none',
  'lib/html-plain-text.ts': 'drops the icon while flattening HTML, draws none',
  'lib/rehype-search-highlight.ts': 'skips the icon while highlighting, draws none',
  'lib/rehype-table-labels.ts': 'skips the icon while labelling cells, draws none',
};

const ICON_SPAN = /material-symbols-outlined[^>]*>\s*([a-z0-9_]+)\s*</g;

/** The icons written in HTML strings anywhere in one locale. */
function localeIcons(tree: unknown, found: Set<string>): Set<string> {
  if (typeof tree === 'string') {
    for (const match of tree.matchAll(ICON_SPAN)) found.add(match[1]);
  } else if (tree && typeof tree === 'object') {
    for (const value of Object.values(tree)) localeIcons(value, found);
  }
  return found;
}

describe('the public icon font', () => {
  it('holds every icon a public page can draw', () => {
    const drawn = new Set([
      ...Object.values(SHOWROOM_DECISION_ICONS),
      ...Object.values(CARD_ACTION_ICONS),
    ]);
    for (const locale of [enDict, frDict, deDict, esDict, itDict, zhDict]) {
      localeIcons(locale, drawn);
    }
    // The demo's call card: an empty scan would make this test pass on nothing.
    expect(drawn).toContain('phone');
    const missing = [...drawn].filter(icon => !MANIFEST.icons.includes(icon)).sort();
    expect(missing, `add them to the manifest's icons, then ${REGENERATE}`).toEqual([]);
  });

  it('knows every module that writes an icon span', () => {
    expect(MODULES.length).toBeGreaterThan(100);
    const readers = filesMatching(MODULES, /material-symbols-outlined/).sort();
    expect(readers).toEqual(Object.keys(ICON_CLASS_READERS).sort());
  });

  it('is the file fetched for exactly those icons and axes', () => {
    const request = new URL(MANIFEST.source);
    expect(request.searchParams.get('icon_names')).toBe([...MANIFEST.icons].sort().join(','));
    expect(request.searchParams.get('family')).toBe(`Material Symbols Outlined:${MANIFEST.axes}`);
    expect(FONT_SHA256, REGENERATE).toBe(MANIFEST.sha256);
  });
});
