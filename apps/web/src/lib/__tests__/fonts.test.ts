/**
 * Fonts are self-hosted — the build must never fetch from Google.
 *
 * Two production image builds failed on 2026-08-16 because next/font/google
 * downloads from fonts.gstatic.com at build time and Google rotated the
 * hosted file versions mid-day (404 on every face, 28 Turbopack errors).
 * These guards pin the remediation:
 *  - no `next/font/google` import may reappear anywhere under src/;
 *  - every woff2 file fonts.ts declares actually exists in the repo, so a
 *    path typo fails here instead of at image-build time.
 *
 * File-based on purpose: importing fonts.ts would require the Next compiler
 * (next/font is a compiler feature), while the contract under test is the
 * source tree itself.
 */

import { createHash } from 'node:crypto';
import { existsSync, readFileSync } from 'node:fs';
import { resolve } from 'node:path';

import { describe, expect, it } from 'vitest';

import { readSources, SRC_ROOT } from '@/__tests__/source-scan';

const FONTS_TS = resolve(__dirname, '../fonts.ts');
const SYMBOLS_DIR = resolve(SRC_ROOT, '../public/fonts/material-symbols');
const SYMBOLS_CSS = readFileSync(resolve(SYMBOLS_DIR, 'material-symbols.css'), 'utf8');
const LAYOUT = readFileSync(resolve(SRC_ROOT, 'app/[lng]/layout.tsx'), 'utf8');
const GLOBAL_CSS = readFileSync(resolve(SRC_ROOT, 'styles/globals.css'), 'utf8');

/** Every `.ts`/`.tsx` file of `src/`, tests included — read at collection (`source-scan.ts`). */
const SOURCES = readSources(file => /\.(ts|tsx)$/.test(file.relative));

describe('self-hosted fonts contract', () => {
  it('serves the full historical icon face from the app origin without CDN hints', () => {
    expect(LAYOUT).not.toMatch(/fonts\.(?:googleapis|gstatic)\.com/);
    expect(GLOBAL_CSS).toContain(
      "@import '../../public/fonts/material-symbols/material-symbols.css'"
    );
    expect(
      GLOBAL_CSS.indexOf('../../public/fonts/material-symbols/material-symbols.css')
    ).toBeGreaterThan(GLOBAL_CSS.indexOf("@import './lia-components.css'"));
    expect(SYMBOLS_CSS).toContain(
      "src: url('/fonts/material-symbols/MaterialSymbolsOutlined.woff2') format('woff2')"
    );
    expect(SYMBOLS_CSS).not.toContain('https://');
    expect(SYMBOLS_CSS).toContain("font-family: 'Material Symbols Outlined'");
    expect(SYMBOLS_CSS).toContain('font-weight: 100 700');
    expect(SYMBOLS_CSS).toContain('font-display: swap');
    expect(SYMBOLS_CSS).toContain("-webkit-font-feature-settings: 'liga'");
    expect(SYMBOLS_CSS).toContain('font-size: 24px');
  });

  it('retains the reviewed variable font and Apache license byte for byte in one canonical location', () => {
    const digest = (file: string) =>
      createHash('sha256')
        .update(readFileSync(resolve(SYMBOLS_DIR, file)))
        .digest('hex');
    expect(digest('MaterialSymbolsOutlined.woff2')).toBe(
      '96c9913f4d415adeefcc3fa13f4f75912648f6f426be8b50e5e20c035b17cdf3'
    );
    expect(digest('LICENSE')).toBe(
      '58d1e17ffe5109a7ae296caafcadfdbe6a7d176f0bc4ab01e12a689b0499d8bd'
    );
    expect(
      existsSync(resolve(SRC_ROOT, '../e2e/fixtures/fonts/MaterialSymbolsOutlined.woff2'))
    ).toBe(false);
  });

  it('no source file imports next/font/google (build-time network dependency)', () => {
    // Match the import form only — prose MENTIONS of the module id (this
    // guard, the fonts.ts docstring explaining the remediation) are fine.
    const importForm = /from ['"]next\/font\/google['"]/;
    const offenders = SOURCES.filter(file => importForm.test(file.text)).map(file => file.relative);
    expect(offenders).toEqual([]);
  });

  it('every woff2 declared in fonts.ts exists in the repo', () => {
    const source = readFileSync(FONTS_TS, 'utf-8');
    const paths = [...source.matchAll(/path: '([^']+\.woff2)'/g)].map(m => m[1]);
    expect(paths.length).toBeGreaterThanOrEqual(23);
    const missing = paths.filter(p => !existsSync(resolve(SRC_ROOT, 'lib', p)));
    expect(missing).toEqual([]);
  });

  it('the seven families keep their CSS variables (rendering contract)', () => {
    const source = readFileSync(FONTS_TS, 'utf-8');
    for (const cssVar of [
      '--font-noto-sans',
      '--font-plus-jakarta',
      '--font-ibm-plex',
      '--font-source-sans',
      '--font-merriweather',
      '--font-libre-baskerville',
      '--font-fira-code',
    ]) {
      expect(source).toContain(`variable: '${cssVar}'`);
    }
  });

  /**
   * Every optional family must opt OUT of preloading.
   *
   * These are user-selectable display fonts, applied one at a time through
   * `data-font`. With the default `preload: true` the browser fetched 26 font
   * files totalling 618 KB on a page that renders only Inter; opting out took
   * it to 3 files and 162 KB (measured in the dev container, 2026-08-23) with
   * an identical render. Inter is declared in `layout.tsx`, not here, and stays
   * preloaded on purpose — it is the default face.
   */
  it('every optional family opts out of preloading', () => {
    const source = readFileSync(FONTS_TS, 'utf-8');
    const declarations = [...source.matchAll(/localFont\(\{([\s\S]*?)\n\}\);/g)].map(m => m[1]);
    expect(declarations.length, 'no localFont() declarations found').toBeGreaterThanOrEqual(7);

    const preloading = declarations.filter(body => !/preload:\s*false/.test(body));
    const named = preloading.map(
      body => /variable: '([^']+)'/.exec(body)?.[1] ?? '(unnamed family)'
    );
    expect(
      named,
      `\nThese optional families would be fetched on every page:\n  ${named.join('\n  ')}\n`
    ).toEqual([]);
  });
});
