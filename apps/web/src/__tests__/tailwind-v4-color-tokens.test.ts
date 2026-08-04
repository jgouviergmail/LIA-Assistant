/**
 * No stylesheet or component may reach for the Tailwind **v3** colour idiom.
 *
 * Tailwind v3 stored colours as bare HSL triplets (`--primary: 217 76% 47%`)
 * and every consumer wrapped them: `hsl(var(--primary))`, `hsl(var(--primary) /
 * 0.5)`. This app is on **v4**, where `@theme` declares whole colours
 * (`--color-primary: oklch(47% 0.13 240)`). The v3 idiom therefore composes to
 * `hsl(oklch(…))`, which is invalid CSS — and the failure is silent in the worst
 * way:
 *
 * - an invalid `fill`/`stroke` on an SVG falls back to **black**;
 * - an invalid colour in a `background`/`box-shadow` makes the declaration drop
 *   entirely, so the element paints **nothing**.
 *
 * Neither shows up in a unit test that asserts roles, names or classes: a black
 * star has the same accessible name as a blue one. Measured 2026-08-04 on the
 * capability constellation (whole chart black) and then found across two
 * charting components and eight stylesheet rules that had been dead for as long
 * as the v4 migration.
 *
 * Two things this guards, and one it deliberately does not:
 *
 * - **`hsl(var(--x))` anywhere under `src/`** — the idiom itself;
 * - **`var(--x)` naming a token that does not exist** — `--primary`,
 *   `--popover`, `--muted` are v3 names with no v4 declaration behind them;
 * - it does NOT forbid `--cosmos-*` globally: those are legitimately scoped to
 *   `.cosmos` on the landing. Their misuse is guarded where it matters, next to
 *   the surface that got it wrong (`constellation-figure.test.ts`).
 */

import { readdirSync, readFileSync, statSync } from 'node:fs';
import { join } from 'node:path';

import { describe, it, expect } from 'vitest';

const SRC = join(__dirname, '..');

/** Every file we could paint with, source and stylesheet alike. */
function walk(dir: string, out: string[] = []): string[] {
  for (const entry of readdirSync(dir)) {
    if (entry === 'node_modules' || entry === '__snapshots__') continue;
    const path = join(dir, entry);
    if (statSync(path).isDirectory()) {
      walk(path, out);
      continue;
    }
    if (/\.(tsx?|css)$/.test(entry) && !/\.test\.tsx?$/.test(entry)) out.push(path);
  }
  return out;
}

const FILES = walk(SRC);
const STYLESHEETS = FILES.filter(path => path.endsWith('.css'));
/**
 * Every custom property the app declares, anywhere.
 *
 * Anchored to the start of a declaration (line start, `{` or `;`) on purpose:
 * a bare `--x\s*:` search also matches inside a SELECTOR — `.lia-btn--primary:hover`
 * reads as a declaration of `--primary`, which made this guard report the very
 * token it exists to catch as "declared".
 */
const DECLARED = new Set(
  STYLESHEETS.flatMap(path =>
    [...readFileSync(path, 'utf8').matchAll(/(?:^|[;{])\s*(--[a-z0-9-]+)\s*:/gm)].map(
      match => match[1]
    )
  )
);

describe('Tailwind v4 colour tokens', () => {
  it('declares the theme tokens this guard is built on', () => {
    // A sanity check on the guard itself: if `@theme` were renamed, every
    // assertion below would pass vacuously.
    for (const token of ['--color-primary', '--color-popover', '--color-border']) {
      expect(DECLARED.has(token), `${token} should be declared`).toBe(true);
    }
    expect(FILES.length).toBeGreaterThan(300);
  });

  it('never wraps a v4 token in the v3 `hsl(var(--x))` idiom', () => {
    const offenders = FILES.filter(path => /hsl\(\s*var\(/.test(readFileSync(path, 'utf8'))).map(
      path => path.slice(SRC.length + 1)
    );

    expect(
      offenders,
      'hsl(var(--x)) composes to hsl(oklch(…)) on Tailwind v4: invalid, and it paints black or nothing'
    ).toEqual([]);
  });

  it('never reads a v3 colour name whose v4 token exists beside it', () => {
    // The precise oracle, and the reason it has no false positives: a `var(--x)`
    // that nothing declares WHILE `--color-x` is declared can only be a leftover
    // v3 name. Runtime-provided properties (`--radix-*`, `--font-*`) and ones
    // set inline from React have no `--color-*` twin, so they never match.
    const stale = new Map<string, string[]>();
    for (const path of FILES) {
      const source = readFileSync(path, 'utf8');
      for (const [, token] of source.matchAll(/var\((--[a-z0-9-]+)/g)) {
        if (DECLARED.has(token)) continue;
        if (!DECLARED.has(`--color-${token.slice(2)}`)) continue;
        const where = path.slice(SRC.length + 1);
        const seen = stale.get(token) ?? [];
        if (!seen.includes(where)) stale.set(token, [...seen, where]);
      }
    }

    expect(
      Object.fromEntries(stale),
      'these are Tailwind v3 colour names; the v4 token is `--color-<name>`'
    ).toEqual({});
  });
});
