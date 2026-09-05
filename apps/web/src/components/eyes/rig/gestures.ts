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
import { bothSides, relative, scaleTapes, type Keys } from '@/components/eyes/rig/choreo';
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
/** Lips pressing together are quick and firm; a corner tugging is light and
 * rings a little, like the smile it almost was. */
const PRESS_SPRING: SpringConfig = { frequency: 4.5, damping: 0.85 };
const TUG_SPRING: SpringConfig = { frequency: 3.4, damping: 0.5 };

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
/**
 * How much a gesture's SIZE may vary from one performance to the next.
 *
 * The host draws a scale in [0.85, 1.15] for each beat it plays; the rig and
 * its tests never do (the default is exactly 1). Only RELATIVE tapes scale —
 * they are offsets from the pose — while an absolute closure (a lid at 1, a
 * mass at 1.07) is a fact that must not be overshot.
 */
export const GESTURE_SCALE_MIN = 0.85;
export const GESTURE_SCALE_SPAN = 0.3;

export function scaleGestureTapes(tapes: readonly Tape[], scale: number): Tape[] {
  return scaleTapes(tapes, scale, true);
}

/** A small relative beat on one channel — the face's secondary action. */
function follow(
  channel: Tape['channel'],
  keys: Keys,
  durationMs: number,
  spring: SpringConfig
): Tape {
  return relative(channel, keys, durationMs, spring);
}

/** The same relative beat on both brows, the right one trailing and moving a
 * hair less — two brows moving as one bar read as a mechanism. */
function browsFollow(
  base: 'browY' | 'browArc',
  keys: Keys,
  durationMs: number,
  spring: SpringConfig
): Tape[] {
  return bothSides(base, keys, durationMs, spring);
}

export function tapesForGesture(gesture: IdleGesture, scale = 1): Tape[] {
  return scaleGestureTapes(gestureTapes(gesture), scale);
}

function gestureTapes(gesture: IdleGesture): Tape[] {
  switch (gesture) {
    case 'slow-blink':
      // A sigh is an exhale: the mouth narrows with the lids and lets go as
      // they reopen. Without it the eyes sigh and the mouth sits it out.
      return [
        ...lidBeat(1, 420, 900, SLOW_BLINK_SPRING, RIGHT_TRAIL_MS),
        {
          channel: 'mouthW',
          keys: [
            { atMs: 0, value: -0.06 },
            { atMs: 420, value: 0 },
          ],
          durationMs: 900,
          spring: SLOW_BLINK_SPRING,
          relative: true,
        },
      ];
    case 'half-blink':
      return lidBeat(0.42, 190, 350, LID_SPRING, 60);
    case 'squint':
      // Squinting scrunches the whole face: the brows come down and
      // flatten, the mouth narrows a touch, all on the lid's own clock.
      return [
        ...lidBeat(0.5, 330, 740, LID_SPRING, 50),
        ...browsFollow(
          'browY',
          [
            [0, 0.02],
            [330, 0],
          ],
          690,
          LID_SPRING
        ),
        ...browsFollow(
          'browArc',
          [
            [0, -0.1],
            [330, 0],
          ],
          690,
          LID_SPRING
        ),
        follow(
          'mouthW',
          [
            [0, -0.05],
            [330, 0],
          ],
          690,
          LID_SPRING
        ),
      ];
    case 'bounce':
      return [
        ...eyeBeat('ty', -0.11, 0.02, 500, 90),
        ...eyeBeat('sy', 0.06, -0.03, 500, 90),
        // Follow-through: the mouth is dragged along a beat late and
        // overshoots on the way back. A hop that leaves the mouth behind is
        // two eyes jumping, not a face.
        {
          channel: 'mouthY',
          keys: [
            { atMs: 60, value: 0.03 },
            { atMs: 290, value: -0.005 },
          ],
          durationMs: 590,
          spring: HOP_SPRING,
          relative: true,
        },
      ];
    case 'brow':
      // Asymmetric by design — "oh?" is one brow, never two. It is the BROW
      // that moves: height, arch and presence together, so the flash reads
      // on a resting face too (the organ predates this gesture's rewrite,
      // which used to lift the right eye instead).
      return [
        {
          channel: 'browYR',
          keys: [{ atMs: 0, value: -0.06 }],
          durationMs: 420,
          spring: HOP_SPRING,
          relative: true,
        },
        {
          channel: 'browArcR',
          keys: [{ atMs: 0, value: 0.45 }],
          durationMs: 420,
          spring: HOP_SPRING,
          relative: true,
        },
        {
          channel: 'browAR',
          keys: [{ atMs: 0, value: 0.5 }],
          durationMs: 420,
          spring: HOP_SPRING,
          relative: true,
        },
      ];
    case 'lip-press':
      // "Hm." Width and curve pull in together and release: the one mouth
      // beat a resting face makes, and it never means anything in particular.
      return [
        {
          channel: 'mouthW',
          keys: [
            { atMs: 0, value: -0.1 },
            { atMs: 240, value: 0 },
          ],
          durationMs: 380,
          spring: PRESS_SPRING,
          relative: true,
        },
        {
          channel: 'mouthCurve',
          keys: [
            { atMs: 0, value: -0.08 },
            { atMs: 240, value: 0 },
          ],
          durationMs: 380,
          spring: PRESS_SPRING,
          relative: true,
        },
      ];
    case 'corner-tug':
      // One corner lifts and lets go — a smirk that did not happen — and the
      // brow on that side lifts a beat later to agree with it. Alone, the
      // corner read as a twitch; with the brow it reads as a thought.
      return [
        follow(
          'mouthSkew',
          [
            [0, 0.18],
            [260, 0],
          ],
          520,
          TUG_SPRING
        ),
        follow(
          'browYL',
          [
            [60, -0.03],
            [320, 0],
          ],
          600,
          TUG_SPRING
        ),
        follow(
          'browArcL',
          [
            [60, 0.25],
            [320, 0],
          ],
          600,
          TUG_SPRING
        ),
      ];
    case 'brow-twitch':
      // Something crossed the mind: both brows lift and arch for a beat and
      // come back down — the quiet face's most frequent sign of an inner life.
      return [
        ...browsFollow(
          'browY',
          [
            [0, -0.04],
            [230, 0],
          ],
          500,
          HOP_SPRING
        ),
        ...browsFollow(
          'browArc',
          [
            [0, 0.3],
            [230, 0],
          ],
          500,
          HOP_SPRING
        ),
      ];
    case 'perk':
      // Attention is a brow raise before it is anything else: the whole
      // pair lifts and arches with the flick of the mass, and settles after.
      return [
        {
          channel: 'mass',
          keys: [{ atMs: 0, value: 1.07 }],
          durationMs: 300,
          spring: HOP_SPRING,
        },
        ...browsFollow('browY', [[0, -0.035]], 500, HOP_SPRING),
        ...browsFollow('browArc', [[0, 0.22]], 500, HOP_SPRING),
      ];
    case 'tilt':
      // A head tilt with a corner of the mouth and one brow in on it — the
      // "oh really?" of a face, in one beat.
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
        follow(
          'mouthSkew',
          [
            [40, 0.12],
            [420, 0],
          ],
          700,
          TUG_SPRING
        ),
        follow(
          'browArcL',
          [
            [40, 0.18],
            [420, 0],
          ],
          700,
          TUG_SPRING
        ),
      ];
    default:
      return [];
  }
}

/** Gestures whose motion the rig owns (the rest are CSS or gaze targets). */
export const RIG_OWNED_GESTURES = Object.keys(GESTURE_DURATION_MS).filter(
  gesture => tapesForGesture(gesture as IdleGesture).length > 0
) as readonly IdleGesture[];
