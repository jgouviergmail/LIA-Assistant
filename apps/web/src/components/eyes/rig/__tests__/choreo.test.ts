/**
 * The shared choreography vocabulary: one trail, one jitter, one scaler for
 * every module that writes tapes.
 */

import { describe, it, expect } from 'vitest';

import {
  absolute,
  bothSides,
  mirrored,
  relative,
  RIGHT_SCALE,
  RIGHT_TRAIL_MS,
  scaleTapes,
} from '@/components/eyes/rig/choreo';

describe('choreo', () => {
  it('writes a relative beat that ends at its release', () => {
    const tape = relative('mouthW', [[0, -0.1]], 380, { frequency: 4, damping: 0.8 });
    expect(tape.relative).toBe(true);
    expect(tape.keys).toEqual([{ atMs: 0, value: -0.1 }]);
    expect(tape.durationMs).toBe(380);
  });

  it('writes an absolute beat with no relative flag', () => {
    const tape = absolute('mass', [[0, 1.05]], 300);
    expect(tape.relative).toBeUndefined();
    expect(tape.spring).toBeUndefined();
  });

  it('trails and scales the right side, and folds its negative zero', () => {
    const [left, right] = bothSides(
      'browY',
      [
        [100, -0.05],
        [400, 0],
      ],
      600
    );
    expect(left.channel).toBe('browYL');
    expect(right.channel).toBe('browYR');
    expect(right.keys[0].atMs).toBe(100 + RIGHT_TRAIL_MS);
    expect(right.keys[0].value).toBeCloseTo(-0.05 * RIGHT_SCALE, 6);
    expect(Object.is(right.keys[1].value, 0)).toBe(true);
    expect(right.durationMs).toBe(600 + RIGHT_TRAIL_MS);
  });

  it('mirrors the right side — the inner ends move together', () => {
    const [left, right] = mirrored(
      'browRot',
      [
        [0, 8],
        [300, 0],
      ],
      500
    );
    expect(right.keys[0].value).toBeCloseTo(-8 * RIGHT_SCALE, 6);
    expect(Object.is(right.keys[1].value, 0)).toBe(true);
    expect(left.keys[0].value).toBe(8);
  });

  it('scales the relative tapes only by default, and everything on request', () => {
    const tapes = [relative('mouthW', [[0, -0.1]], 300), absolute('blinkL', [[0, 1]], 300)];
    const relativeOnly = scaleTapes(tapes, 1.5);
    expect(relativeOnly[0].keys[0].value).toBeCloseTo(-0.15, 6);
    expect(relativeOnly[1].keys[0].value).toBe(1);
    const everything = scaleTapes(tapes, 1.5, false);
    expect(everything[1].keys[0].value).toBe(1.5);
    // The identity scale returns a copy, never the same array.
    const same = scaleTapes(tapes, 1);
    expect(same).not.toBe(tapes);
    expect(same).toEqual(tapes);
  });
});
