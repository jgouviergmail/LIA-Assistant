/**
 * A brow is never drawn on its eye (owner rule, 2026-11-12) — the half of that
 * rule a unit test can hold.
 *
 * The sheet stops the brow above the eye by reserving, under the top of the
 * brow's box, the room its ink takes: `--brow-floor` (how far down the box the
 * contour reaches when level) and `--brow-pitch` (how much lower one end goes
 * per degree of tilt). Those are numbers about a contour that is drawn
 * ELSEWHERE, by `browPath` and `sculptedBrowPath`. A contour redrawn a little
 * lower with the sheet left alone puts the brow back on the eye, silently, on
 * every character: this file samples the real contours over everything the
 * rig can ask of them and holds the sheet's reserve above them.
 *
 * The other half — where the eye actually starts, on a texture with a
 * transparent margin, under a lid — is paint, and belongs to the browser
 * (`e2e/smoke/chat-avatar-brows.spec.ts`).
 */

import { readFileSync } from 'node:fs';
import { join } from 'node:path';
import { describe, expect, it } from 'vitest';

import { restChannelValues, type ChannelValues } from '@/components/eyes/rig/channels';
import { browPath, sculptedBrowPath } from '@/components/eyes/rig/face-geometry';

const CSS = readFileSync(join(process.cwd(), 'src/styles/eyes.css'), 'utf8');

/** The viewBox every brow is drawn in (`ExpressiveEyes`), top to bottom. */
const BOX_UNITS = 36;

function rule(selector: string): string {
  const start = CSS.indexOf(selector);
  if (start < 0) throw new Error(`no rule ${selector}`);
  return CSS.slice(start, CSS.indexOf('\n}', start));
}

function numberIn(text: string, pattern: RegExp, what: string): number {
  const match = text.match(pattern);
  if (!match) throw new Error(`the sheet no longer states ${what}`);
  return Number(match[1]);
}

const BASE = rule('.lia-eye-brow {');
const SCULPTED = rule(".lia-eye-brow:has([data-rig-brow-shape='sculpted']) {");

/** What the sheet reserves for a stroked brow, in viewBox units from the top
 * of its box: its own formula, read from its own text. */
function strokedReserve(weight: number, degrees: number): number {
  const centre = numberIn(
    BASE,
    /--brow-floor:\s*calc\(\((\d+) \+ var\(--brow-ink\)/,
    'the stroke centre'
  );
  const half = numberIn(
    BASE,
    /var\(--brow-ink\) \* ([\d.]+) \* var\(--brow-weight\)\) \/ 36\)/,
    'half the ink'
  );
  const ink = numberIn(BASE, /--brow-ink:\s*(\d+);/, 'the ink');
  const pitch = numberIn(BASE, /--brow-pitch:\s*([\d.]+);/, 'the stroked pitch');
  return centre + ink * half * weight + pitch * Math.abs(degrees);
}

/** The same for a sculpted brow: the lower of its ends and of its belly. */
function sculptedReserve(weight: number, arc: number, degrees: number): number {
  const ends = SCULPTED.match(/(\d+) \+ (\d+) \* var\(--brow-weight\),/);
  const belly = SCULPTED.match(
    /(\d+) - (\d+) \* clamp\(0, var\(--brow-arc\), 1\) \+ (\d+) \* var\(--brow-weight\)/
  );
  if (!ends || !belly) throw new Error('the sheet no longer states the sculpted floor');
  const pitch = numberIn(SCULPTED, /--brow-pitch:\s*([\d.]+);/, 'the sculpted pitch');
  const level = Math.max(
    Number(ends[1]) + Number(ends[2]) * weight,
    Number(belly[1]) - Number(belly[2]) * arc + Number(belly[3]) * weight
  );
  return level + pitch * Math.abs(degrees);
}

type Point = readonly [number, number];

/** The lowest point a contour reaches (the largest y), sampled along its
 * curves — absolute `M`, `C`, `Q` and `Z`, which is all the two writers emit. */
function lowestPoint(path: string): number {
  const tokens = path.match(/[MCQZ]|-?[\d.]+/g) ?? [];
  let cursor: Point = [0, 0];
  let lowest = -Infinity;
  const read = (index: number): Point => [Number(tokens[index]), Number(tokens[index + 1])];
  const walk = (points: readonly Point[]) => {
    for (let step = 0; step <= 64; step += 1) {
      const t = step / 64;
      // De Casteljau, for a curve of any degree.
      let level = points.map(point => point[1]);
      while (level.length > 1) level = level.slice(1).map((y, i) => level[i] + (y - level[i]) * t);
      lowest = Math.max(lowest, level[0]);
    }
    cursor = points[points.length - 1];
  };
  for (let index = 0; index < tokens.length; ) {
    const command = tokens[index];
    if (command === 'M') {
      cursor = read(index + 1);
      lowest = Math.max(lowest, cursor[1]);
      index += 3;
    } else if (command === 'C') {
      walk([cursor, read(index + 1), read(index + 3), read(index + 5)]);
      index += 7;
    } else if (command === 'Q') {
      walk([cursor, read(index + 1), read(index + 3)]);
      index += 5;
    } else if (command === 'Z') {
      index += 1;
    } else {
      throw new Error(`a brow contour grew a command this guard cannot read: ${command}`);
    }
  }
  return lowest;
}

function face(side: 'L' | 'R', arc: number, rotation: number, weight: number): ChannelValues {
  return {
    ...restChannelValues(),
    [`browArc${side}`]: arc,
    [`browRot${side}`]: rotation,
    [`browS${side}`]: weight,
  };
}

const ARCS = [0, 0.06, 0.12, 0.3, 0.6, 1];
const ROTATIONS = [-30, -18, -7, 0, 7, 18, 30];
const WEIGHTS = [0.94, 1, 1.06];

describe('the room the sheet keeps under a brow', () => {
  it('stops a sculpted brow by the very clip its eye takes', () => {
    // A smile closes a sculpted eye from both sides (`--spirit-squint`), and
    // the lid line the brow stops above is that clip's upper edge. Two
    // spellings of the squint would let the eye close under a brow that
    // still thinks it open: one declaration, on the box both inherit from.
    expect(CSS.match(/--spirit-squint:/g)).toHaveLength(1);
    expect(rule('.lia-spirit-companion .lia-eye {')).toContain('--spirit-squint:');
    const shape = rule('.lia-spirit-companion .lia-eye-shape {');
    expect(shape).toMatch(
      /inset\(\s*max\(\s*calc\(var\(--lid-top\) \+ var\(--spirit-squint\) \* var\(--oy\)\),/
    );
    expect(rule('.lia-spirit-companion .lia-eye-brow {')).toContain(
      '--eye-lid-line: calc(var(--lid-top) + var(--spirit-squint) * var(--oy));'
    );
  });

  it('covers every sculpted contour the rig can draw, on both sides', () => {
    let tightest = Infinity;
    for (const side of ['L', 'R'] as const)
      for (const arc of ARCS)
        for (const rotation of ROTATIONS)
          for (const weight of WEIGHTS) {
            const drawn = lowestPoint(sculptedBrowPath(face(side, arc, rotation, weight), side));
            const reserved = sculptedReserve(weight, arc, rotation);
            expect(
              reserved,
              `sculpted ${side}, arc ${arc}, ${rotation}°, weight ${weight}`
            ).toBeGreaterThanOrEqual(drawn - 1e-9);
            tightest = Math.min(tightest, reserved - drawn);
          }
    // ...and it is the contour's own measure, not a generous guess: somewhere
    // the reserve is within a unit of the ink (a thirty-sixth of the box).
    expect(tightest).toBeLessThan(1);
  });

  it('covers every stroked contour, its round ends included', () => {
    const ink = numberIn(BASE, /--brow-ink:\s*(\d+);/, 'the ink');
    let tightest = Infinity;
    for (const side of ['L', 'R'] as const)
      for (const arc of ARCS)
        for (const rotation of ROTATIONS)
          for (const weight of WEIGHTS) {
            // A stroke reaches half its width below its centre line, and a
            // round cap reaches no further.
            const drawn =
              lowestPoint(browPath(face(side, arc, rotation, weight), side)) + (ink * weight) / 2;
            const reserved = strokedReserve(weight, rotation);
            expect(
              reserved,
              `stroked ${side}, arc ${arc}, ${rotation}°, weight ${weight}`
            ).toBeGreaterThanOrEqual(drawn - 1e-9);
            tightest = Math.min(tightest, reserved - drawn);
          }
    expect(tightest).toBeLessThan(1);
  });

  it('draws the ink the sheet counts, in the box the sheet counts it in', () => {
    // The reserve is a share of the brow's own height: it only means anything
    // while the contour is drawn in that many units...
    expect(BASE).toMatch(/var\(--brow-h\) \*\s+var\(--brow-floor\)/);
    expect(BASE).toMatch(/var\(--brow-h\) \* var\(--brow-pitch\) \* var\(--brow-degrees\) \/ 36/);
    expect(CSS).toMatch(/\.lia-eye-brow svg \{[^}]*height:\s*var\(--brow-h\)/);
    // ...with the ink the stroke rule draws, and no other.
    expect(CSS).toContain('stroke-width: calc(var(--brow-ink) * 1px * var(--brow-weight))');
    expect(CSS.match(/stroke-width:[^;]*brow/g)).toHaveLength(1);
    expect(BOX_UNITS).toBe(36);
  });

  it('turns the tilt into a number the way the contour reads it, to the degree', () => {
    // The sheet cannot divide an angle: it rebuilds the degrees from the
    // tangent and the sine. Wrong by more than a fraction of a degree, the
    // reserve under a tilted brow would be short by that much ink.
    const factor = numberIn(
      BASE,
      /2 \* sin\(var\(--brow-rot\)\)\) \* ([\d.]+),/,
      'the degrees factor'
    );
    for (const degrees of ROTATIONS) {
      const radians = (degrees * Math.PI) / 180;
      const rebuilt = (Math.tan(radians) + 2 * Math.sin(radians)) * factor;
      expect(Math.abs(rebuilt - degrees)).toBeLessThan(0.15);
    }
    expect(BASE).toMatch(/--brow-degrees:\s*clamp\(\s*-30,/);
  });

  it('places the brow by the smaller of its authored spot and the limit above the eye', () => {
    const placement = BASE.slice(BASE.indexOf('translate:'));
    expect(placement).toMatch(
      /min\(\s*calc\(var\(--brow-anchor\) - var\(--brow-lift\) \+ var\(--brow-y\)\),/
    );
    expect(placement).toMatch(
      /var\(--eye-crest\) \+ var\(--eye-slope\) \* var\(--brow-x\) - var\(--brow-clear\)/
    );
    expect(placement).toMatch(/max\(var\(--brow-skew\), -1 \* var\(--brow-skew\)\)/);
    // A line of skin, not a touch: at the widget's sizes this is a pixel —
    // at the size it is SEEN, so a face its screen draws smaller keeps more.
    expect(numberIn(BASE, /--brow-skin:\s*([\d.]+)em;/, 'the skin kept')).toBeGreaterThanOrEqual(
      0.02
    );
    expect(BASE).toContain('--brow-clear: var(--brow-skin);');
    expect(rule('.lia-monitor .lia-eye-brow {')).toContain(
      '--brow-clear: calc(var(--brow-skin) / var(--monitor-face-scale));'
    );
  });
});
