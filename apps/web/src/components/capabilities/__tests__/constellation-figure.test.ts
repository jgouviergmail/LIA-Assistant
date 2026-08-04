/**
 * The constellation's geometry, and the tokens it paints itself with.
 *
 * Two defects this file exists to prevent, both measured in a browser on
 * 2026-08-04 and both invisible to every other test in this folder:
 *
 *  1. **the figure crossed itself.** Joining the lit stars in LAYOUT order
 *     (inner ring, then outer) draws a knot: the path jumps from the inner
 *     circle to the outer one and back. A constellation is read as an outline,
 *     so the order has to be ANGULAR, which is the one ordering that cannot
 *     self-intersect around an interior point;
 *  2. **the drawing rendered BLACK.** The SVG asked for `hsl(var(--primary))`,
 *     a Tailwind v3 idiom. This app is on v4, where the token is
 *     `--color-primary: oklch(…)`; `hsl(oklch(…))` is invalid, and an invalid
 *     `fill` falls back to black. Every unit test still passed — they assert
 *     roles and names, and a black star has the same accessible name as a blue
 *     one. So the oracle here is the STYLESHEET: every custom property the
 *     chart paints with must actually be declared in `globals.css`.
 */

import { readFileSync } from 'node:fs';
import { join } from 'node:path';

import { describe, it, expect } from 'vitest';

import {
  CAPABILITY_ORDER,
  backdropStars,
  figureOutline,
  layoutCapabilities,
} from '../constellation-layout';
import { activeLabel, nodeName } from '../capability-state';

const ALL = CAPABILITY_ORDER.map(entry => entry.key);

/** Angle of a point around the box centre, in radians. */
function angleOf(point: { x: number; y: number }): number {
  return Math.atan2(point.y - 50, point.x - 50);
}

describe('figureOutline', () => {
  it('keeps only the lit stars', () => {
    const positions = layoutCapabilities(ALL);
    const lit = new Set(['memory', 'relations', 'journals']);

    const outline = figureOutline(positions, position => lit.has(position.key));

    expect(new Set(outline.map(p => p.key))).toEqual(lit);
  });

  it('orders them by angle, so the outline cannot cross itself', () => {
    const positions = layoutCapabilities(ALL);
    // Deliberately mixing both rings: this is the case that knotted.
    const lit = new Set(['memory', 'skills', 'connectors', 'journals', 'relations']);

    const outline = figureOutline(positions, position => lit.has(position.key));

    const angles = outline.map(angleOf);
    expect(angles).toEqual([...angles].sort((a, b) => a - b));
  });

  it('draws nothing from a single lit star — one star is not a constellation', () => {
    const positions = layoutCapabilities(ALL);

    expect(figureOutline(positions, p => p.key === 'memory')).toEqual([]);
    expect(figureOutline(positions, () => false)).toEqual([]);
  });

  it('draws a segment from two', () => {
    const positions = layoutCapabilities(ALL);

    const outline = figureOutline(positions, p => p.key === 'memory' || p.key === 'journals');

    expect(outline).toHaveLength(2);
  });
});

describe('backdropStars', () => {
  const field = backdropStars();

  it('is deterministic — the sky is the same on every visit', () => {
    expect(backdropStars()).toEqual(field);
  });

  it('stays inside the box', () => {
    for (const star of field) {
      expect(star.x).toBeGreaterThanOrEqual(0);
      expect(star.x).toBeLessThanOrEqual(100);
      expect(star.y).toBeGreaterThanOrEqual(0);
      expect(star.y).toBeLessThanOrEqual(100);
    }
  });

  it('leaves the nucleus and the rings alone', () => {
    // Dust over the capabilities themselves would read as extra nodes, which
    // is the one thing the map must never do: every dot is a claim.
    for (const star of field) {
      const distance = Math.hypot(star.x - 50, star.y - 50);
      expect(distance === 0 || distance > 14).toBe(true);
    }
  });
});

describe('the chart paints itself with tokens that are in scope', () => {
  const root = join(__dirname, '..', '..', '..');
  const css = readFileSync(join(root, 'styles', 'globals.css'), 'utf8');
  const sources = [
    'CapabilityConstellation.tsx',
    'ConstellationSky.tsx',
    'CapabilityList.tsx',
  ].map(name =>
    readFileSync(join(root, 'components', 'capabilities', name), 'utf8')
  );
  // The chart's own stylesheet block, plus every `var()` its markup reads.
  const styleBlock = css.slice(css.indexOf('.capability-'));
  const readTokens = sources
    .flatMap(source => [...source.matchAll(/var\((--[a-z0-9-]+)/g)].map(match => match[1]))
    .concat([...styleBlock.matchAll(/var\((--[a-z0-9-]+)/g)].map(match => match[1]));

  it('never reaches for the Tailwind v3 `hsl(var(--x))` idiom', () => {
    // The exact defect: valid on v3, invalid on v4, and it renders BLACK.
    for (const source of [...sources, styleBlock]) {
      expect(source).not.toMatch(/hsl\(\s*var\(/);
    }
  });

  it('never borrows a token scoped to the landing page', () => {
    // `--cosmos-*` is declared under `.cosmos`, a class the dashboard does not
    // carry: reading one here resolves to NOTHING, and the gradient that asked
    // for it simply does not paint. Same cost as the black fill, quieter.
    for (const token of readTokens) {
      expect(token, 'a `.cosmos`-scoped token is out of scope here').not.toMatch(/^--cosmos-/);
    }
  });

  it('never paints scene text with a token that flips with the theme', () => {
    // The scene keeps its own night in BOTH themes — a star chart is a
    // nocturnal instrument, and the landing already reads that way. The
    // consequence is strict: `text-foreground` and `text-muted-foreground`
    // invert to near-black in light mode and would leave the labels
    // unreadable ON the night. Scene text uses the scene's own ink.
    const [constellation] = sources;
    // Bounded to `Star` — the only text drawn ON the night. The legend under
    // the chart sits on the page background and must follow the theme, so
    // sweeping the whole file would forbid the correct thing there.
    const scene = constellation.slice(
      constellation.indexOf('function Star'),
      constellation.indexOf('export function CapabilityConstellation')
    );
    for (const flipping of ['text-foreground', 'text-muted-foreground', 'ring-ring']) {
      expect(scene, `${flipping} inverts with the theme, the scene does not`).not.toContain(
        flipping
      );
    }
  });

  it('declares every custom property it reads, at document scope', () => {
    for (const token of readTokens) {
      // `--capability-delay` is the one property the markup SETS inline, per
      // star; everything else must be declared in the stylesheet.
      if (token === '--capability-delay') continue;
      expect(
        token.startsWith('--color-') || token.startsWith('--capability-'),
        `${token} is neither a theme token nor one of the chart's own`
      ).toBe(true);
      expect(css, `${token} is painted but never declared`).toContain(`${token}:`);
    }
  });
});

describe('a capability with no tally is never given one', () => {
  // ADR-185: a count shown to the user is exact, or it does not exist.
  // `personality` and `proactivity` are switches, and `detail ?? 0` turned
  // "no tally" into "0 item(s)" — an active capability reading as empty.
  const t = ((key: string, opts?: Record<string, unknown>) =>
    opts ? `${key}|${JSON.stringify(opts)}` : key) as unknown as Parameters<
    typeof activeLabel
  >[0];

  it('says plain "active" in the list when there is nothing to count', () => {
    expect(activeLabel(t, { key: 'personality', active: true, detail: null })).toBe(
      'capabilities.state_active_plain'
    );
  });

  it('still counts what can be counted', () => {
    expect(activeLabel(t, { key: 'memory', active: true, detail: 12 })).toBe(
      'capabilities.state_active|{"count":12}'
    );
    // Zero is a REAL count when the capability does tally: an empty inbox is
    // not the same claim as a capability that keeps no tally at all.
    expect(activeLabel(t, { key: 'memory', active: true, detail: 0 })).toBe(
      'capabilities.state_active|{"count":0}'
    );
  });

  it("applies the same rule to the star's accessible name", () => {
    expect(nodeName(t, { key: 'personality', active: true, detail: null }, 'Personality')).toBe(
      'capabilities.node_active_plain|{"name":"Personality"}'
    );
    expect(nodeName(t, { key: 'voice', active: false, detail: null }, 'Voice')).toBe(
      'capabilities.node_dormant|{"name":"Voice"}'
    );
  });
});
