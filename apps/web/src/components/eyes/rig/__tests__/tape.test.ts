/**
 * Tapes — timed target sequences, and the anticipation they make possible.
 *
 * The step semantics are the point: keys are held, not interpolated, so the
 * spring between two keys is what draws the curve. That is what turns a
 * two-key tape into a real anticipation arc instead of a linear ramp.
 */

import { describe, it, expect } from 'vitest';
import {
  anticipationTape,
  tapeDurationMs,
  tapeTargetAt,
  type Tape,
} from '@/components/eyes/rig/tape';

const BLINK: Tape = {
  channel: 'blinkL',
  keys: [
    { atMs: 0, value: 1 },
    { atMs: 130, value: 0 },
  ],
};

describe('tapeDurationMs', () => {
  it('defaults to the last key', () => {
    expect(tapeDurationMs(BLINK)).toBe(130);
  });

  it('honours an explicit hold beyond the last key', () => {
    expect(tapeDurationMs({ ...BLINK, durationMs: 400 })).toBe(400);
  });

  it('never shrinks below the last key', () => {
    expect(tapeDurationMs({ ...BLINK, durationMs: 10 })).toBe(130);
  });

  it('is zero for an empty tape', () => {
    expect(tapeDurationMs({ channel: 'blinkL', keys: [] })).toBe(0);
  });
});

describe('tapeTargetAt', () => {
  it('holds each key until the next one (steps, never a ramp)', () => {
    expect(tapeTargetAt(BLINK, 0)).toBe(1);
    expect(tapeTargetAt(BLINK, 129)).toBe(1);
    expect(tapeTargetAt(BLINK, 130)).toBe(0);
  });

  it('releases the channel once the tape is over', () => {
    expect(tapeTargetAt(BLINK, 131)).toBeNull();
    expect(tapeTargetAt(BLINK, -1)).toBeNull();
  });

  it('holds the last key through an explicit hold', () => {
    const held = { ...BLINK, durationMs: 400 };
    expect(tapeTargetAt(held, 300)).toBe(0);
    expect(tapeTargetAt(held, 401)).toBeNull();
  });

  it('returns null for an empty tape rather than inventing a target', () => {
    expect(tapeTargetAt({ channel: 'blinkL', keys: [] }, 0)).toBeNull();
  });

  it('treats a first key after zero as a START DELAY (the per-eye trail)', () => {
    const delayed: Tape = {
      channel: 'blinkR',
      keys: [
        { atMs: 70, value: 1 },
        { atMs: 200, value: 0 },
      ],
    };
    expect(tapeTargetAt(delayed, 0)).toBeNull();
    expect(tapeTargetAt(delayed, 69)).toBeNull();
    expect(tapeTargetAt(delayed, 70)).toBe(1);
    expect(tapeTargetAt(delayed, 200)).toBe(0);
  });
});

describe('anticipationTape', () => {
  const options = { ratio: 0.14, leadMs: 90, minDelta: 0.08 };

  it('pulls AWAY from the destination before committing', () => {
    const tape = anticipationTape('syL', 1, 0.55, options);
    expect(tape).not.toBeNull();
    // Moving down to 0.55, so the eye first rises above its current 1.
    expect(tape!.keys[0].value).toBeGreaterThan(1);
    expect(tapeDurationMs(tape!)).toBe(90);
  });

  it('scales with the move, in the opposite direction', () => {
    const small = anticipationTape('syL', 1, 1.2, options)!;
    const large = anticipationTape('syL', 1, 2, options)!;
    expect(small.keys[0].value).toBeLessThan(1);
    expect(large.keys[0].value).toBeLessThan(small.keys[0].value);
  });

  it('declines moves too small to anticipate (a twitch is not intent)', () => {
    expect(anticipationTape('syL', 1, 1.02, options)).toBeNull();
  });

  it('caps the counter-move so a huge travel cannot fling the eye', () => {
    const capped = anticipationTape('rotL', 0, 90, { ...options, minDelta: 1, maxOffset: 3 })!;
    expect(capped.keys[0].value).toBe(-3);
  });
});
