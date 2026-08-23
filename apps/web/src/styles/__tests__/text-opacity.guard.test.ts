/**
 * Dimmed-text ratchet — `text-<token>/<NN>` may only ever get rarer.
 *
 * A Tailwind opacity modifier on a text colour composites the glyphs against
 * whatever sits behind them, so the pair the reader sees is the BLEND, not the
 * token the code names. `design-contrast.guard.test.ts` guards the tokens; this
 * file guards what the components do to them.
 *
 * The floor is DERIVED, never hardcoded: for every `text-<token>/<NN>` found in
 * the source, the worst ratio across all ten shipped palettes is recomputed
 * from `globals.css`. Re-tune a palette and this guard re-tunes with it — a
 * hardcoded threshold would silently stop matching the product.
 *
 * Ground selection matters, and getting it wrong manufactures false positives:
 * `text-primary-foreground/90` measured 1.00:1 against `background`, which is
 * meaningless — `primary-foreground` only ever sits on `primary`. Every
 * `*-foreground` token is therefore measured against its own solid; the rest
 * against `background` and `card`, the two grounds the pair matrix already
 * assumes.
 *
 * Measured 2026-08-23 on 127 dimmed usages: `text-foreground/90` (43 sites) and
 * `text-foreground/80` (28) clear AA and are simply legal. The rest sit below
 * it. They are NOT mass-rewritten here — most are icons or decoration, whose
 * real threshold is 3:1 and whose context this scan cannot see, and rewriting
 * ~50 unexamined sites would be exactly the kind of blind sweep that causes
 * the regressions it claims to prevent. They are FROZEN instead: the baseline
 * records what exists, new ones fail, and each removal ratchets it down.
 */

import { readdirSync, readFileSync, statSync } from 'node:fs';
import { join, relative, resolve } from 'node:path';

import { describe, it, expect } from 'vitest';

import { type Palette, allPalettes, blend, contrast } from './contrast-math';

const SRC = resolve(__dirname, '../..');
const BASELINE_PATH = resolve(__dirname, 'text-opacity-baseline.json');

/** WCAG 1.4.3 AA for normal text. */
const AA = 4.5;

const palettes = allPalettes();

/**
 * The ground a token is actually painted on.
 *
 * `*-foreground` tokens are the label colour of their own solid surface; every
 * other token is body/accent text on a neutral ground.
 */
function groundsFor(token: string, p: Palette): Palette[string][] {
  const solid = token.replace(/-foreground$/, '');
  if (token.endsWith('-foreground') && token !== 'foreground' && p[solid]) {
    return [p[solid]];
  }
  return [p['background'], p['card']];
}

/** Worst-case contrast of `text-<token>/<opacity>` across every shipped palette. */
export function worstRatio(token: string, opacity: number): number {
  let worst = Number.POSITIVE_INFINITY;
  for (const p of Object.values(palettes)) {
    const fg = p[token];
    if (!fg) continue;
    for (const ground of groundsFor(token, p)) {
      if (!ground) continue;
      worst = Math.min(worst, contrast(blend(fg, ground, opacity / 100), ground));
    }
  }
  return worst;
}

/** Every `--color-*` token name the palettes define, longest first so the regex is greedy-correct. */
const TOKENS = Object.keys(palettes['default-light']).sort((a, b) => b.length - a.length);

const DIM_RE = new RegExp(`text-(${TOKENS.join('|')})/(\\d{1,3})\\b`, 'g');

function walk(dir: string): string[] {
  const out: string[] = [];
  for (const entry of readdirSync(dir)) {
    if (entry === 'node_modules' || entry === '__tests__') continue;
    const full = join(dir, entry);
    if (statSync(full).isDirectory()) out.push(...walk(full));
    else if (/\.tsx?$/.test(full)) out.push(full);
  }
  return out;
}

/** Count sub-AA dimmed text usages, per source file. */
export function scanDimUsages(): Record<string, number> {
  const counts: Record<string, number> = {};
  for (const file of walk(SRC)) {
    const source = readFileSync(file, 'utf-8');
    let dim = 0;
    for (const m of source.matchAll(DIM_RE)) {
      if (worstRatio(m[1], Number(m[2])) < AA) dim++;
    }
    if (dim > 0) counts[relative(SRC, file).replace(/\\/g, '/')] = dim;
  }
  return counts;
}

describe('dimmed-text ratchet (text-<token>/<opacity>)', () => {
  const baseline: Record<string, number> = JSON.parse(readFileSync(BASELINE_PATH, 'utf-8'));
  const current = scanDimUsages();

  it('introduces no dimmed text in a file that had none', () => {
    const added = Object.keys(current).filter(f => !(f in baseline));
    expect(
      added,
      `\nThese files gained sub-AA dimmed text (text-<token>/<opacity>).\n` +
        `Use the full-strength token, or a non-text element if it is decoration:\n  ${added.join('\n  ')}\n`
    ).toEqual([]);
  });

  it('never increases the count in a file that already had some', () => {
    const grown = Object.entries(current)
      .filter(([f, n]) => f in baseline && n > baseline[f])
      .map(([f, n]) => `${f}: ${baseline[f]} -> ${n}`);
    expect(grown, `\nDimmed-text count grew (the ratchet only turns down):\n  ${grown.join('\n  ')}\n`).toEqual(
      []
    );
  });

  it('has no stale baseline entries (lower the baseline after cleaning a file)', () => {
    const stale = Object.entries(baseline)
      .filter(([f, n]) => (current[f] ?? 0) < n)
      .map(([f, n]) => `${f}: baseline ${n}, actual ${current[f] ?? 0}`);
    expect(
      stale,
      `\nThese files improved — lower the baseline to lock the gain in:\n  ${stale.join('\n  ')}\n`
    ).toEqual([]);
  });

  it('derives the floor from globals.css rather than hardcoding it', () => {
    // The two legal patterns, and the first one below the line: if a palette
    // edit moves these, the guard has genuinely re-tuned rather than drifted.
    expect(worstRatio('foreground', 90)).toBeGreaterThanOrEqual(AA);
    expect(worstRatio('foreground', 80)).toBeGreaterThanOrEqual(AA);
    expect(worstRatio('muted-foreground', 70)).toBeLessThan(AA);
  });

  it('measures *-foreground tokens against their own solid, not the page', () => {
    // Guards the false positive this scan was built around: `primary-foreground`
    // on `background` reads 1.00:1 and means nothing.
    expect(worstRatio('primary-foreground', 90)).toBeGreaterThan(4);
  });
});
