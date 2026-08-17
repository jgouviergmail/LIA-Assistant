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

import { existsSync, readdirSync, readFileSync, statSync } from 'node:fs';
import { join, resolve } from 'node:path';

import { describe, expect, it } from 'vitest';

const SRC_ROOT = resolve(__dirname, '../..');
const FONTS_TS = resolve(__dirname, '../fonts.ts');

function walk(dir: string): string[] {
  return readdirSync(dir).flatMap(entry => {
    const full = join(dir, entry);
    if (statSync(full).isDirectory()) {
      return entry === 'node_modules' || entry === '__snapshots__' ? [] : walk(full);
    }
    return /\.(ts|tsx)$/.test(entry) ? [full] : [];
  });
}

describe('self-hosted fonts contract', () => {
  it('no source file imports next/font/google (build-time network dependency)', () => {
    // Match the import form only — prose MENTIONS of the module id (this
    // guard, the fonts.ts docstring explaining the remediation) are fine.
    const importForm = /from ['"]next\/font\/google['"]/;
    const offenders = walk(SRC_ROOT).filter(file =>
      importForm.test(readFileSync(file, 'utf-8'))
    );
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
});
