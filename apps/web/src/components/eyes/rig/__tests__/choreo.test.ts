/**
 * The shared choreography vocabulary: one trail, one jitter, one scaler for
 * every module that writes tapes.
 */

import { describe, it, expect } from 'vitest';

import {
  absolute,
  bothSides,
  flipTapes,
  mirrored,
  relative,
  RIGHT_SCALE,
  RIGHT_TRAIL_MS,
  scaleTapes,
  WARP_AMPLITUDE_JITTER,
  WARP_CHANNEL_TIME_JITTER,
  WARP_PACE_MIN,
  WARP_PACE_SPAN,
  warpTapes,
  withRelease,
} from '@/components/eyes/rig/choreo';
import { tapeDurationMs } from '@/components/eyes/rig/tape';

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

describe('flipTapes', () => {
  it('mirrors a one-sided beat: sides swap, signed lateral channels negate, the rest is kept', () => {
    const flipped = flipTapes([
      relative('browYR', [[0, -0.06]], 420),
      relative('browArcL', [[0, 0.3]], 420),
      relative('mouthSkew', [[0, 0.18]], 500),
      absolute('tilt', [[0, 3.5]], 700),
      relative('mouthW', [[0, -0.1]], 300),
      absolute('gazeX', [[0, 0.7]], 300),
      relative('rotL', [[0, -5]], 300),
    ]);
    expect(flipped.map(tape => tape.channel)).toEqual([
      'browYL',
      'browArcR',
      'mouthSkew',
      'tilt',
      'mouthW',
      'gazeX',
      'rotR',
    ]);
    const value = (index: number) => flipped[index].keys[0].value;
    expect(value(0)).toBe(-0.06);
    expect(value(1)).toBe(0.3);
    expect(value(2)).toBe(-0.18);
    expect(value(3)).toBe(-3.5);
    expect(value(4)).toBe(-0.1);
    expect(value(5)).toBe(-0.7);
    // A per-eye rotation is mirrored: it swaps sides AND changes sign.
    expect(value(6)).toBe(5);
    // Folded negative zero: a flipped 0 is still written as 0.
    expect(Object.is(flipTapes([relative('tilt', [[0, 0]], 100)])[0].keys[0].value, 0)).toBe(true);
  });
});

describe('warpTapes', () => {
  const scene = [
    relative(
      'mouthCurve',
      [
        [0, 0.6],
        [200, 0.4],
      ],
      600,
      { frequency: 4, damping: 0.8 }
    ),
    relative('browYL', [[80, -0.05]], 640),
    relative('browYR', [[120, -0.046]], 680),
    absolute('mass', [[0, 1.05]], 500),
  ];

  it('is the identity at the middle of every draw', () => {
    const same = warpTapes(scene, () => 0.5);
    expect(same).toEqual(scene);
  });

  it('paces the whole performance, then jitters TIME and SIZE per channel — the two brows differ', () => {
    // One draw for the pace, then per channel one for time and one for size.
    const sequence = [0, 1, 1, 0, 0, 1, 0.5, 0.5];
    let index = 0;
    const warped = warpTapes(scene, () => sequence[index++ % sequence.length]);
    const pace = WARP_PACE_MIN; // draw 0
    // mouthCurve: time draw 1 (+jitter), size draw 1 (+jitter).
    const curve = warped[0];
    const timeFactor = pace * (1 + WARP_CHANNEL_TIME_JITTER);
    expect(curve.keys.map(key => key.atMs)).toEqual([0, Math.round(200 * timeFactor)]);
    expect(curve.durationMs).toBe(Math.round(600 * timeFactor));
    expect(curve.keys[0].value).toBeCloseTo(0.6 * (1 + WARP_AMPLITUDE_JITTER), 6);
    expect(curve.spring).toEqual(scene[0].spring);
    // The brows are two channels: two different draws, two different brows.
    const left = warped[1];
    const right = warped[2];
    expect(left.keys[0].value).toBeCloseTo(-0.05 * (1 - WARP_AMPLITUDE_JITTER), 6);
    // (the right brow drew 0.5 for its size: exactly as written)
    expect(right.keys[0].value).toBeCloseTo(-0.046, 6);
    expect(left.keys[0].atMs).toBe(Math.round(80 * pace * (1 - WARP_CHANNEL_TIME_JITTER)));
    expect(right.keys[0].atMs).toBe(Math.round(120 * pace * (1 + WARP_CHANNEL_TIME_JITTER)));
    // An absolute tape is paced but never resized: a mass at 1.05 is a fact.
    const mass = warped[3];
    expect(mass.keys[0].value).toBe(1.05);
    expect(mass.durationMs).not.toBe(500);
  });

  it('keeps one time factor per CHANNEL, so a hold and its release stay joined', () => {
    const held = withRelease(scene.slice(0, 1), { frequency: 2, damping: 1 });
    const warped = warpTapes(held, () => 0.9);
    expect(tapeDurationMs(warped[0])).toBe(warped[1].keys[0].atMs);
  });

  it('never leaves the pace band: the slowest and the fastest performances', () => {
    const slow = warpTapes(scene, () => 0);
    const fast = warpTapes(scene, () => 1);
    expect(slow[0].durationMs).toBe(
      Math.round(600 * WARP_PACE_MIN * (1 - WARP_CHANNEL_TIME_JITTER))
    );
    expect(fast[0].durationMs).toBe(
      Math.round(600 * (WARP_PACE_MIN + WARP_PACE_SPAN) * (1 + WARP_CHANNEL_TIME_JITTER))
    );
    expect(WARP_PACE_MIN).toBeLessThan(1);
    expect(WARP_PACE_MIN + WARP_PACE_SPAN).toBeGreaterThan(1);
  });
});

describe('withRelease', () => {
  it('appends, per relative tape, a release that hands the channel home on ITS spring', () => {
    const spring = { frequency: 1.2, damping: 1 };
    const scene = [
      relative('mouthCurve', [[0, 0.6]], 600, { frequency: 4, damping: 0.8 }),
      absolute('mass', [[0, 1.05]], 500),
    ];
    const released = withRelease(scene, spring);
    expect(released.slice(0, 2)).toEqual(scene);
    expect(released).toHaveLength(3);
    const release = released[2];
    expect(release.channel).toBe('mouthCurve');
    expect(release.relative).toBe(true);
    expect(release.release).toBe(true);
    expect(release.keys).toEqual([{ atMs: 600, value: 0 }]);
    expect(release.spring).toEqual(spring);
    // It lasts as long as its spring needs to settle, then lets the pose go on.
    expect(release.durationMs).toBe(600 + Math.round(1057 / spring.frequency));
  });
});
