/**
 * Guard: Tailwind must only ever scan the application sources.
 *
 * Tailwind v4 auto-detects its sources from the working directory and turns
 * every file it finds into a webpack dependency. In the dev container that
 * directory is a 9p bind-mount where one stat() costs ~1.5-2.8 ms, so a
 * generated tree left next to the sources is paid on every scan AND on every
 * cache validation. Measured 2026-08-23 with three leftover `.next-e2e*`
 * proof dists in place: 35 331 files scanned (96 % of them build artefacts),
 * 449 s to compile globals.css, and 10 min 32 s for the first page — 9 s once
 * the scan was scoped.
 *
 * The fix is the explicit `source(none)` + `@source` pair in globals.css. This
 * test fails if anyone drops it, if the glob stops covering the sources, if
 * the dependency set starts growing again, or if a test is scanned again — no
 * test ships, so none is a source of the stylesheet (the `@source not` pair).
 */
import { readFileSync } from 'node:fs';
import path from 'node:path';

import postcss from 'postcss';
import { describe, expect, it } from 'vitest';

import tailwind from '@tailwindcss/postcss';

const WEB_ROOT = path.resolve(__dirname, '../../..');
const GLOBALS = path.join(WEB_ROOT, 'src/styles/globals.css');

/**
 * Upper bound on the files Tailwind may declare as dependencies.
 *
 * Shrink-only, like every other ratchet here: `src` held 1 265 scannable files
 * on 2026-08-23, so this leaves room for the app to grow without leaving room
 * for a build-artefact tree (the smallest one measured added 11 163 files by
 * itself). Lower it when the real number drops; never raise it to absorb a
 * directory that should not be scanned in the first place.
 *
 * On 2026-10-14 the scan crossed it at 2 504 files, 1 064 of them tests: the
 * tests left the scan, and the 1 440 production sources left are still above
 * the 1 265 this bound was calibrated on — so it stays where it is.
 */
const MAX_SCANNED_FILES = 2500;

/** What the `@source not` pair of globals.css keeps out of the scan. */
const isTestFile = (file: string): boolean =>
  /(^|\/)__tests__\//.test(file) || /\.(test|spec)\.(ts|tsx|js|jsx|mjs|cjs)$/.test(file);

const compile = async () =>
  postcss([tailwind({ base: WEB_ROOT })]).process(readFileSync(GLOBALS, 'utf8'), {
    from: GLOBALS,
    to: path.join(WEB_ROOT, '.next/tailwind-source-scope-guard.css'),
  });

describe('tailwind source scope', () => {
  it('never falls back to automatic source detection', () => {
    const css = readFileSync(GLOBALS, 'utf8');
    expect(css).toMatch(/@import\s+['"]tailwindcss['"]\s+source\(none\)/);
    expect(css).toMatch(/@source\s+['"][^'"]+['"]/);
  });

  it('scans the sources, and nothing but the sources', async () => {
    const result = await compile();

    const dependencies = result.messages
      .filter(message => message.type === 'dependency')
      .map(message => path.relative(WEB_ROOT, String(message.file)).split(path.sep).join('/'));

    // Lower bound too: a collapsed scan would silently ship a stylesheet with
    // most utilities missing, which no assertion on the CSS text would catch.
    expect(dependencies.length).toBeGreaterThan(800);
    expect(dependencies.length).toBeLessThan(MAX_SCANNED_FILES);

    // Tailwind's own entry stylesheet is a legitimate rebuild dependency; any
    // OTHER path outside `src/` means the scan has escaped the sources again.
    const strays = dependencies.filter(
      file => !file.startsWith('src/') && !file.includes('node_modules/')
    );
    expect(strays).toEqual([]);

    expect(dependencies.filter(isTestFile)).toEqual([]);
  });

  it('still generates the utilities the app actually uses', async () => {
    const result = await compile();

    // One witness per family a narrowed scan would plausibly break: the custom
    // `mobile` breakpoint declared in @theme (880px), a colour with arbitrary
    // opacity, and a variant-prefixed utility — the last two staples of the
    // design system, so restyling one component cannot red this guard. Tests
    // are not scanned, so only production code can produce a witness: until
    // 2026-10-14 this file's own text produced the bare `border-amber-200` and
    // `not-sr-only` it named, so those two could not fail.
    expect(result.css).toContain('880px');
    expect(result.css).toContain('bg-primary\\/10');
    expect(result.css).toContain('focus-visible\\:ring-2');
  });
});
