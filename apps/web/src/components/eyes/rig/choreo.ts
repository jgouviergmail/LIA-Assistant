/**
 * Choreography helpers — the vocabulary every tape-writing module shares.
 *
 * Arrivals (`scripts.ts`), gestures (`gestures.ts`), the face's own life
 * (`life.ts`) and the sketches (`sketches.ts`) all write tapes, and they all
 * need the same three sentences: a RELATIVE beat (an offset from the pose,
 * ended at its release), an ABSOLUTE beat (for channels whose rest value is
 * the reference: the mass, the head tilt, the gaze), and the same beat on
 * BOTH sides with the right one trailing and moving a hair less — two
 * halves moving as one bar read as a mechanism. Written four times, the
 * trail and the jitter had already started to drift between files.
 */

import type { ChannelKey, EyeChannelBase } from '@/components/eyes/rig/channels';
import type { SpringConfig } from '@/components/eyes/rig/spring';
import type { Tape, TapeKey } from '@/components/eyes/rig/tape';

/** `[atMs, value]` pairs — a timeline reads as a table, not as objects. */
export type Keys = readonly (readonly [number, number])[];

/** The right side trails the left by this much, everywhere. */
export const RIGHT_TRAIL_MS = 40;
/** ...and moves a hair less: two eyes doing the same thing at the same
 * size, however offset in time, still read as a mechanism. */
export const RIGHT_SCALE = 0.92;

function toKeys(keys: Keys): TapeKey[] {
  return keys.map(([atMs, value]) => ({ atMs, value }));
}

/**
 * A relative beat: keys are OFFSETS from the pose. It ENDS at `durationMs`,
 * where the channel is handed back to the pose and eases home on the
 * expression's own dynamics — the slow-out is not a key, it is the end.
 */
export function relative(
  channel: ChannelKey,
  keys: Keys,
  durationMs: number,
  spring?: SpringConfig
): Tape {
  return { channel, keys: toKeys(keys), durationMs, spring, relative: true };
}

/** An absolute beat — for channels whose rest value IS the reference (the
 * mass, the head tilt, the gaze, a blink closure). */
export function absolute(
  channel: ChannelKey,
  keys: Keys,
  durationMs: number,
  spring?: SpringConfig
): Tape {
  return { channel, keys: toKeys(keys), durationMs, spring };
}

/** The right side's keys: trailed and scaled. `+ 0` folds the negative zero
 * a scaled or mirrored 0 would otherwise produce. */
function rightKeys(keys: Keys, sign: 1 | -1, trailMs: number): Keys {
  return keys.map(([atMs, value]) => [atMs + trailMs, sign * value * RIGHT_SCALE + 0] as const);
}

/** The same relative beat on BOTH sides, the right one trailing. */
export function bothSides(
  base: EyeChannelBase,
  keys: Keys,
  durationMs: number,
  spring?: SpringConfig,
  trailMs = RIGHT_TRAIL_MS
): Tape[] {
  return [
    relative(`${base}L`, keys, durationMs, spring),
    relative(`${base}R`, rightKeys(keys, 1, trailMs), durationMs + trailMs, spring),
  ];
}

/** A MIRRORED relative pair — the left value and its negation on the right
 * (a tilt of the inner ends, a lean of the eyes). */
export function mirrored(
  base: EyeChannelBase,
  keys: Keys,
  durationMs: number,
  spring?: SpringConfig,
  trailMs = RIGHT_TRAIL_MS
): Tape[] {
  return [
    relative(`${base}L`, keys, durationMs, spring),
    relative(`${base}R`, rightKeys(keys, -1, trailMs), durationMs + trailMs, spring),
  ];
}

/** Scale every key of a performance for the occasion — RELATIVE tapes only
 * when `relativeOnly` is set: an absolute closure (a lid at 1, a gaze at the
 * edge) is a fact, not an offset. */
export function scaleTapes(tapes: readonly Tape[], scale: number, relativeOnly = true): Tape[] {
  if (scale === 1) return [...tapes];
  return tapes.map(tape =>
    relativeOnly && !tape.relative
      ? tape
      : { ...tape, keys: tape.keys.map(key => ({ ...key, value: key.value * scale })) }
  );
}
