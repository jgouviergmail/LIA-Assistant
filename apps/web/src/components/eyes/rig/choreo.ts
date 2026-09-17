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

import {
  EYE_CHANNEL_BASES,
  type ChannelKey,
  type EyeChannel,
  type EyeChannelBase,
  type EyeSide,
} from '@/components/eyes/rig/channels';
import type { SpringConfig } from '@/components/eyes/rig/spring';
import { tapeDurationMs, type Tape, type TapeKey } from '@/components/eyes/rig/tape';

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

/** Global channels whose sign is a DIRECTION on the screen's horizontal
 * axis: a mirror image negates them. */
const FLIP_NEGATED: ReadonlySet<ChannelKey> = new Set([
  'mouthSkew',
  'mouthX',
  'tilt',
  'massX',
  'gazeX',
  'hlX',
  'stretchA',
]);

/** Per-eye channels that mean "toward the other eye" or "clockwise": a
 * mirror image swaps their side AND negates them. */
const FLIP_NEGATED_BASES: ReadonlySet<EyeChannelBase> = new Set([
  'rot',
  'baseRot',
  'browRot',
  'browX',
  'tx',
]);

/** The per-eye base and side of a channel, or null for a global one. */
function eyeChannelParts(channel: ChannelKey): { base: EyeChannelBase; side: EyeSide } | null {
  for (const base of EYE_CHANNEL_BASES) {
    if (channel === `${base}L`) return { base, side: 'L' };
    if (channel === `${base}R`) return { base, side: 'R' };
  }
  return null;
}

function negated(tape: Tape, channel: ChannelKey): Tape {
  return { ...tape, channel, keys: tape.keys.map(key => ({ ...key, value: -key.value + 0 })) };
}

/**
 * The MIRROR IMAGE of a performance: every per-eye channel changes side, and
 * every channel whose sign is a screen direction changes sign. A one-sided
 * beat written once (a raised brow, a corner tug, a head tilt) is thereby
 * played on either side — the same beat on the same side every time is a
 * mechanism, and the owner asked for each brow to have a life of its own.
 */
export function flipTapes(tapes: readonly Tape[]): Tape[] {
  return tapes.map(tape => {
    const parts = eyeChannelParts(tape.channel);
    if (parts) {
      const mirrored: EyeChannel = `${parts.base}${parts.side === 'L' ? 'R' : 'L'}`;
      return FLIP_NEGATED_BASES.has(parts.base)
        ? negated(tape, mirrored)
        : { ...tape, channel: mirrored };
    }
    return FLIP_NEGATED.has(tape.channel) ? negated(tape, tape.channel) : tape;
  });
}

/**
 * WARP a performance for the occasion — the reason no two performances of
 * one scene are ever alike.
 *
 * Measured on the running widget (2026-09-17): every mouth beat reached half
 * its travel at 50 ms, ninety per cent at 100 ms and its peak at 150 ms, on
 * the same spring, held the same time, let go the same way — a curve the
 * eye learns in a minute. One draw sets the PACE of the whole performance
 * (a little slower or quicker than written); then every CHANNEL draws its
 * own time jitter and, for a relative tape, its own size, so the two brows
 * of one grin lift by different amounts at different instants and the eyes
 * squash unevenly. One factor per channel, not per tape: a hold and its
 * release must stay joined. Absolute tapes are paced but never resized — a
 * lid at 1 and a mass at 1.05 are facts.
 */
export const WARP_PACE_MIN = 0.85;
export const WARP_PACE_SPAN = 0.3;
export const WARP_CHANNEL_TIME_JITTER = 0.06;
export const WARP_AMPLITUDE_JITTER = 0.12;

interface ChannelWarp {
  readonly time: number;
  readonly size: number;
}

/** A draw in [0, 1] mapped to `1 ± jitter`. */
function jitter(draw: number, amount: number): number {
  return 1 + (draw - 0.5) * 2 * amount;
}

export function warpTapes(tapes: readonly Tape[], random: () => number): Tape[] {
  const pace = WARP_PACE_MIN + random() * WARP_PACE_SPAN;
  const byChannel = new Map<ChannelKey, ChannelWarp>();
  const warpFor = (channel: ChannelKey): ChannelWarp => {
    const known = byChannel.get(channel);
    if (known) return known;
    const warp = {
      time: pace * jitter(random(), WARP_CHANNEL_TIME_JITTER),
      size: jitter(random(), WARP_AMPLITUDE_JITTER),
    };
    byChannel.set(channel, warp);
    return warp;
  };
  return tapes.map(tape => {
    const { time, size } = warpFor(tape.channel);
    const scale = tape.relative ? size : 1;
    return {
      ...tape,
      keys: tape.keys.map(key => ({
        atMs: Math.round(key.atMs * time),
        value: key.value * scale + 0,
      })),
      durationMs: tape.durationMs === undefined ? undefined : Math.round(tape.durationMs * time),
    };
  });
}

/** Settling time (99 %) of a critically damped spring, in ms per Hz. */
const SETTLE_MS_PER_HZ = 1057;

/**
 * Give a scene its OWN way home.
 *
 * A relative tape ends at its release and the channel eases home on the
 * expression's dynamics — the same 650 ms for a grin let go and a smack
 * snapped shut. Every scene now appends, per relative tape, a RELEASE tape:
 * one key at the pose, starting where the hold ends, driven by the scene's
 * own spring for as long as that spring needs to settle. A sulk lingers on
 * a heavy spring; a smack snaps back on a quick one; and past the release
 * the pose's dynamics finish what little is left, continuously.
 */
export function withRelease(tapes: readonly Tape[], spring: SpringConfig): Tape[] {
  const windowMs = Math.round(SETTLE_MS_PER_HZ / spring.frequency);
  const releases = tapes
    .filter(tape => tape.relative)
    .map(tape => {
      const endMs = tapeDurationMs(tape);
      return {
        channel: tape.channel,
        keys: [{ atMs: endMs, value: 0 }],
        durationMs: endMs + windowMs,
        spring,
        relative: true,
        release: true,
      };
    });
  return [...tapes, ...releases];
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
