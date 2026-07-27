/**
 * Viewport-unit guard (S2) — height constraints use the DYNAMIC viewport.
 *
 * `100vh` is the LARGE viewport: the height the page would have if the
 * browser's dynamic UI (URL bar, toolbars) were retracted. While those bars are
 * visible — which is the state a page loads in on mobile — an element sized in
 * `vh` is taller than what the user can actually see, and its bottom is pushed
 * off-screen. On the chat shell that bottom is the composer: the one control
 * the page exists for.
 *
 * `dvh` tracks the viewport as the bars come and go, which is what every
 * height-constrained surface here wants.
 *
 * Scope, deliberately narrow: this guard covers declarations that CONSTRAIN a
 * height (`h-`, `min-h-`, `max-h-`, and the CSS `height` / `max-height`
 * properties). It ignores:
 *   - `vw` units — the horizontal viewport has no dynamic-bar equivalent;
 *   - `sizes=` image hints — media descriptors, not layout;
 *   - purely decorative heights (the snowfall effect), which are listed as
 *     explicit, justified exemptions below.
 *
 * Shrink-only: the exemption list may lose entries, never gain them without a
 * written reason.
 */

import { readFileSync, readdirSync, statSync } from 'node:fs';
import { join, relative } from 'node:path';

import { describe, it, expect } from 'vitest';

const SRC = join(process.cwd(), 'src');

/**
 * Height declarations that legitimately keep `vh`.
 *
 * `SnowfallEffect` sizes a purely decorative overlay to a sixth of the
 * viewport; whether that band tracks the URL bar is immaterial, and the effect
 * is `aria-hidden` scenery.
 */
const EXEMPT: ReadonlyArray<{ file: string; reason: string }> = [
  {
    file: 'components/effects/SnowfallEffect.tsx',
    reason: 'decorative overlay band, not a layout constraint',
  },
];

/** Tailwind height utilities and raw CSS height properties, using `vh`. */
const TAILWIND_HEIGHT_VH = /\b(?:max-|min-)?h-\[[^\]]*?\d+vh[^\]]*?\]/g;
// Covers both CSS (`max-height: 80vh`) and inline-style camelCase
// (`maxHeight: '90vh'`). `[^;\n]` on purpose: without excluding newlines, an
// unrelated `height: auto` on one line would pair with a `90vh` several lines
// below and report a phantom offender.
const CSS_HEIGHT_VH = /(?:max-|min-|max|min)?[hH]eight:\s*['"]?[^;\n]*?\d+vh/gm;

function walk(dir: string): string[] {
  const out: string[] = [];
  for (const entry of readdirSync(dir)) {
    const full = join(dir, entry);
    if (statSync(full).isDirectory()) {
      if (entry === '__tests__' || entry === 'node_modules') continue;
      out.push(...walk(full));
    } else if (/\.(tsx?|css)$/.test(entry)) {
      out.push(full);
    }
  }
  return out;
}

describe('viewport-unit guard', () => {
  const offenders: Array<{ file: string; match: string }> = [];

  for (const file of walk(SRC)) {
    const rel = relative(SRC, file).replace(/\\/g, '/');
    if (EXEMPT.some(e => e.file === rel)) continue;
    const source = readFileSync(file, 'utf8');
    for (const regex of [TAILWIND_HEIGHT_VH, CSS_HEIGHT_VH]) {
      for (const match of source.match(regex) ?? []) {
        // ONE tolerated pattern: a `vh` declaration kept as an explicit
        // fallback next to its `supports-[height:100dvh]:` counterpart. Any
        // other `dvh` on the line (a sibling utility, an unrelated property)
        // must NOT whitelist the offender.
        const line = source.split('\n').find(l => l.includes(match.trim())) ?? '';
        if (line.includes('supports-[height:100dvh]:')) continue;
        offenders.push({ file: rel, match: match.trim() });
      }
    }
  }

  it('constrains no height with the large viewport alone', () => {
    expect(
      offenders,
      'height constraints must use dvh (or pair vh with a dvh fallback):\n' +
        offenders.map(o => `  ${o.file}: ${o.match}`).join('\n')
    ).toEqual([]);
  });

  /**
   * Self-tests: a scanner that silently stops matching is worse than no
   * scanner — it reports "clean" forever. These drive the two regexes over
   * synthetic samples so a refactor of the patterns cannot rot unnoticed.
   */
  describe('the detector actually detects', () => {
    const hits = (source: string): string[] => [
      ...(source.match(TAILWIND_HEIGHT_VH) ?? []),
      ...(source.match(CSS_HEIGHT_VH) ?? []),
    ];

    it.each([
      ['tailwind height', 'className="h-[calc(100vh-5rem)]"'],
      ['tailwind max-height', 'className="max-h-[90vh] overflow-y-auto"'],
      ['tailwind min-height', 'className="min-h-[60vh]"'],
      ['responsive variant', 'className="h-[92vh] sm:h-[88vh]"'],
      ['css property', '  max-height: 80vh;'],
      ['inline camelCase style', "style={{ maxHeight: '90vh' }}"],
    ])('catches a %s', (_label, sample) => {
      expect(hits(sample).length).toBeGreaterThan(0);
    });

    it.each([
      ['a width', 'className="max-w-[85vw]"'],
      ['an image sizes hint', 'sizes="(max-width: 768px) 100vw, 768px"'],
      ['an already-converted height', 'className="max-h-[90dvh]"'],
      ['an unrelated height', "style={{ height: 'auto' }}"],
    ])('ignores %s', (_label, sample) => {
      expect(hits(sample)).toEqual([]);
    });

    it('does not let a newline pair an unrelated height with a later vh', () => {
      // The bug this exact regex was fixed for: `[^;]` crossed line breaks.
      const sample = "style={{ height: 'auto' }}\n<div className='x'>\n  top: 90vh;";
      expect(hits(sample).some(m => m.includes("height: 'auto'"))).toBe(false);
    });
  });

  it('keeps the exemption list justified, minimal and CURRENT', () => {
    for (const { file, reason } of EXEMPT) {
      expect(reason.length, `${file} needs a written reason`).toBeGreaterThan(20);
      expect(() => statSync(join(SRC, file)), `${file} no longer exists`).not.toThrow();

      // Refuse a STALE entry (ADR-155 model): an exemption whose file no
      // longer contains a `vh` height silently widens the blind spot for
      // whatever is added to that file next.
      const source = readFileSync(join(SRC, file), 'utf8');
      const stillNeedsIt =
        (source.match(TAILWIND_HEIGHT_VH) ?? []).length > 0 ||
        (source.match(CSS_HEIGHT_VH) ?? []).length > 0;
      expect(stillNeedsIt, `${file} no longer constrains a height in vh — drop its exemption`).toBe(
        true
      );
    }
  });
});
