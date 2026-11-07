/**
 * The scale a health dial draws (owner, 2026-11-06): three equal bands whose edges are the bounds
 * the card has always coloured a figure by, and a position that never leaves the dial.
 */
import { describe, expect, it } from 'vitest';

import { bandArc, bandOf, dialPosition, HEALTH_SCALES, toneOf } from '../health-dial';

const { steps, heart_rate: heart } = HEALTH_SCALES;

describe('the bands', () => {
  it.each([
    [steps, 0, 'red'],
    [steps, 5000, 'red'],
    [steps, 5001, 'orange'],
    [steps, 9999, 'orange'],
    [steps, 10000, 'green'],
    [steps, 50000, 'green'],
    [heart, 0, 'green'],
    [heart, 70, 'green'],
    [heart, 71, 'orange'],
    [heart, 89, 'orange'],
    [heart, 90, 'red'],
    [heart, 200, 'red'],
  ] as const)('reads %# as the card always coloured it', (scale, value, tone) => {
    expect(toneOf(scale, value)).toBe(tone);
  });

  it('names the band a value stands in, in the order of the dial', () => {
    expect([bandOf(steps, 5000), bandOf(steps, 5001), bandOf(steps, 10000)]).toEqual([0, 1, 2]);
  });
});

describe('the position on the dial', () => {
  it('sets the bounds at a third and two thirds of it, whatever the unit', () => {
    for (const scale of [steps, heart]) {
      expect(dialPosition(scale, scale.bounds[0])).toBeCloseTo(1 / 3);
      expect(dialPosition(scale, scale.bounds[1])).toBeCloseTo(2 / 3);
    }
  });

  it('keeps a value beyond the scale at its end, the figure saying the rest', () => {
    expect(dialPosition(steps, 50000)).toBe(1);
    expect(dialPosition(steps, -1)).toBe(0);
    expect(dialPosition(heart, 30)).toBe(0);
    expect(dialPosition(heart, 180)).toBe(1);
  });
});

describe('the bands as drawn', () => {
  it('leaves a gap between two bands and none at the ends of the dial', () => {
    const [first, second, third] = [0, 1, 2].map(band => bandArc(band));

    expect(first?.from).toBe(0);
    expect(third?.to).toBe(1);
    expect(first?.to).toBeLessThan(second?.from ?? 0);
    expect(second?.to).toBeLessThan(third?.from ?? 0);
  });
});
