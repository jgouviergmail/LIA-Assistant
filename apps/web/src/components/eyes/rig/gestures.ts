/**
 * Blinks and idle gestures, as tapes.
 *
 * These used to be CSS keyframes on `clip-path` and `transform`, which is
 * exactly the set of properties the rig now writes every frame — a keyframe
 * REPLACES the property it animates, so the two could not coexist. Expressed
 * as tapes they compose instead: a half-blink during joy lowers the lid over
 * joy's dome rather than cancelling it, and a bounce lifts an eye from
 * wherever the expression put it (hence `relative`).
 *
 * Two gesture families deliberately stay in CSS: the gaze wander (it is a
 * gaze target, not a beat) and the four slapstick beats, which ride the
 * INDEPENDENT `translate` / `scale` / `rotate` properties and therefore
 * compose with the rig's transforms without touching them.
 */

import { GESTURE_DURATION_MS, type IdleGesture } from '@/components/eyes/expression-engine';
import type { Tape } from '@/components/eyes/rig/tape';
import type { SpringConfig } from '@/components/eyes/rig/spring';

/** A blink is fast whatever mood the face is in — hence its own spring,
 * underdamped so the reopening overshoots: that rebound is the "flesh" a
 * purely geometric lid was missing. */
const BLINK_SPRING: SpringConfig = { frequency: 6.2, damping: 0.72 };
const SLOW_BLINK_SPRING: SpringConfig = { frequency: 2.2, damping: 0.9 };
const LID_SPRING: SpringConfig = { frequency: 3.6, damping: 0.95 };
/** A hop rings: low damping is the whole point of a bounce. */
const HOP_SPRING: SpringConfig = { frequency: 2.6, damping: 0.42 };

/** The right eye always trails — a perfectly synchronous pair reads mechanical. */
const RIGHT_TRAIL_MS = 70;

/**
 * One spontaneous blink.
 *
 * The tape outlives its last key on purpose: holding the channel through the
 * REOPENING is what keeps the fast blink spring in charge of it. Released at
 * the closing key, the reopening would inherit the expression's own dynamics
 * and a drowsy face would snap its eyes open.
 */
export function blinkTapes(): Tape[] {
  return [
    {
      channel: 'blinkL',
      keys: [
        { atMs: 0, value: 1 },
        { atMs: 130, value: 0 },
      ],
      durationMs: 300,
      spring: BLINK_SPRING,
    },
    {
      channel: 'blinkR',
      keys: [
        { atMs: RIGHT_TRAIL_MS, value: 1 },
        { atMs: 130 + RIGHT_TRAIL_MS, value: 0 },
      ],
      durationMs: 300 + RIGHT_TRAIL_MS,
      spring: BLINK_SPRING,
    },
  ];
}

/** A lid beat on both eyes, the right one trailing. */
function lidBeat(
  closure: number,
  releaseAtMs: number,
  durationMs: number,
  spring: SpringConfig,
  trailMs: number
): Tape[] {
  return [
    {
      channel: 'blinkL',
      keys: [
        { atMs: 0, value: closure },
        { atMs: releaseAtMs, value: 0 },
      ],
      durationMs,
      spring,
    },
    {
      channel: 'blinkR',
      keys: [
        { atMs: trailMs, value: closure },
        { atMs: releaseAtMs + trailMs, value: 0 },
      ],
      durationMs: durationMs + trailMs,
      spring,
    },
  ];
}

/** A relative beat on one channel of both eyes, the right one trailing. */
function eyeBeat(
  base: 'ty' | 'sy',
  peak: number,
  settle: number,
  durationMs: number,
  trailMs: number
): Tape[] {
  const keys = (offset: number) => [
    { atMs: offset, value: peak },
    { atMs: 230 + offset, value: settle },
  ];
  return [
    {
      channel: `${base}L`,
      keys: keys(0),
      durationMs,
      spring: HOP_SPRING,
      relative: true,
    },
    {
      channel: `${base}R`,
      keys: keys(trailMs),
      durationMs: durationMs + trailMs,
      spring: HOP_SPRING,
      relative: true,
    },
  ];
}

/**
 * The tapes an idle gesture plays.
 *
 * Returns an empty list for the gestures the rig does not own: the two gaze
 * moves (a target, not a beat) and the slapstick beats (CSS, on independent
 * properties). Total tape duration never exceeds `GESTURE_DURATION_MS` for
 * that gesture, so the motion and the state the host holds agree — a beat
 * still playing after the host cleared its gesture would be an orphan.
 */
export function tapesForGesture(gesture: IdleGesture): Tape[] {
  switch (gesture) {
    case 'slow-blink':
      return lidBeat(1, 420, 900, SLOW_BLINK_SPRING, RIGHT_TRAIL_MS);
    case 'half-blink':
      return lidBeat(0.42, 190, 350, LID_SPRING, 60);
    case 'squint':
      return lidBeat(0.5, 330, 740, LID_SPRING, 50);
    case 'bounce':
      return [...eyeBeat('ty', -0.11, 0.02, 500, 90), ...eyeBeat('sy', 0.06, -0.03, 500, 90)];
    case 'brow':
      // Asymmetric by design — "oh?" is one brow, never two.
      return [
        {
          channel: 'tyR',
          keys: [{ atMs: 0, value: -0.06 }],
          durationMs: 420,
          spring: HOP_SPRING,
          relative: true,
        },
        {
          channel: 'syR',
          keys: [{ atMs: 0, value: 0.12 }],
          durationMs: 420,
          spring: HOP_SPRING,
          relative: true,
        },
      ];
    case 'perk':
      return [
        {
          channel: 'mass',
          keys: [{ atMs: 0, value: 1.07 }],
          durationMs: 300,
          spring: HOP_SPRING,
        },
      ];
    case 'tilt':
      return [
        {
          channel: 'tilt',
          keys: [
            { atMs: 0, value: 3.5 },
            { atMs: 300, value: -2.2 },
          ],
          durationMs: 700,
          spring: { frequency: 2, damping: 0.5 },
        },
      ];
    default:
      return [];
  }
}

/** Gestures whose motion the rig owns (the rest are CSS or gaze targets). */
export const RIG_OWNED_GESTURES = Object.keys(GESTURE_DURATION_MS).filter(
  gesture => tapesForGesture(gesture as IdleGesture).length > 0
) as readonly IdleGesture[];
