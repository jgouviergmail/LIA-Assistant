/**
 * Sketches — the little scenes a resting character plays now and then.
 *
 * The face's own life (`life.ts`) gives a quiet face a mimic every ten
 * seconds or so: one beat, one thought. A SKETCH is a different register: a
 * three to five second piece of acting with a beginning, a turn and an end
 * — the eyes chase a fly and lose it, a double take at nothing, a sneeze
 * that builds and lands, a doze that snaps awake — played rarely enough to
 * be a small event (every 45 to 120 s, never two close together) and
 * written to be funny, surprising and a little Pixar. It is what makes the
 * avatar a character instead of a status light.
 *
 * Mechanically a sketch is one thing: a set of tapes whose keys span the
 * whole scene, on every channel the rig owns — the gaze (absolute: the
 * scene decides where the eyes look), the blinks, the eye shapes, the mass
 * and the head, the brows, the mouth and the ink. The rig plays them
 * together, one-shot beats (a spontaneous blink, a host gesture) still win
 * over them, and the scene is DROPPED the moment the expression changes: a
 * sketch never plays over a reaction, a search or a speech. Every relative
 * tape is handed back at its end and eases home on the expression's own
 * dynamics, and every absolute one returns to its rest before it ends, so
 * the face is exactly where it was when the curtain falls.
 */

import { absolute, bothSides, mirrored, relative, type Keys } from '@/components/eyes/rig/choreo';
import type { SpringConfig } from '@/components/eyes/rig/spring';
import type { Tape } from '@/components/eyes/rig/tape';
import type { EyeExpression } from '@/components/eyes/expression-engine';

/** The resting expressions a sketch may interrupt — the ones that breathe,
 * minus a thought in progress (a face working a problem is not idle). */
export const SKETCH_EXPRESSIONS: ReadonlySet<EyeExpression> = new Set([
  'neutral',
  'attentive',
  'tender',
  'joy',
  'bored',
  'tired',
]);

/** Pause between two sketches, uniformly drawn. Far apart on purpose: a
 * scene every minute or two is an event, every twenty seconds a routine. */
export const SKETCH_MIN_DELAY_MS = 45_000;
export const SKETCH_MAX_DELAY_MS = 120_000;

/** A sketch lasts between three and five seconds — a piece, not a beat. */
export const SKETCH_MIN_MS = 3000;
export const SKETCH_MAX_MS = 5000;

/** The face's own life stands aside for the scene and a breath after it. */
export const SKETCH_MOUTH_GRACE_MS = 2500;

// --- Springs: how each kind of move is reached.
/** A saccade JUMPS. */
const SACCADE: SpringConfig = { frequency: 6.5, damping: 1 };
/** A cartoon hit: quick, a discreet ring. */
const PUNCH: SpringConfig = { frequency: 4.2, damping: 0.65 };
/** An eased move. */
const EASE: SpringConfig = { frequency: 2.4, damping: 0.9 };
/** A slow, heavy settle — a doze, a stretch. */
const HEAVY: SpringConfig = { frequency: 1.5, damping: 1 };
/** A lid: fast, with the reopening rebound that gives a blink its flesh. */
const LID: SpringConfig = { frequency: 6.2, damping: 0.72 };
const SLOW_LID: SpringConfig = { frequency: 2.2, damping: 0.9 };

/** Where the eyes LOOK: absolute gaze keys, with the catch-lights sent the
 * same way (they chase the gaze on their own slow spring). */
function look(x: Keys, y: Keys, durationMs: number, spring: SpringConfig = SACCADE): Tape[] {
  return [
    absolute('gazeX', x, durationMs, spring),
    absolute('gazeY', y, durationMs, spring),
    absolute('hlX', x, durationMs),
    absolute('hlY', y, durationMs),
  ];
}

/** A blink at `atMs`, held `holdMs` shut, both eyes, the right one trailing. */
function blinkAt(atMs: number, holdMs = 130, closure = 1, spring: SpringConfig = LID): Tape[] {
  const keys: Keys = [
    [atMs, closure],
    [atMs + holdMs, 0],
  ];
  const durationMs = atMs + holdMs + 170;
  return [
    absolute('blinkL', keys, durationMs, spring),
    absolute(
      'blinkR',
      keys.map(([t, v]) => [t + 70, v] as const),
      durationMs + 70,
      spring
    ),
  ];
}

/** Full ink on the mouth and the brows from `atMs` to the end of the scene. */
function ink(keys: Keys, durationMs: number): Tape[] {
  return [
    relative('mouthA', keys, durationMs, PUNCH),
    relative('browAL', keys, durationMs, PUNCH),
    relative('browAR', keys, durationMs, PUNCH),
  ];
}

/** Gaze keys tracing `turns` circles of radius `amp`, one key per `stepMs`. */
function circle(fromMs: number, turns: number, periodMs: number, amp: number, stepMs: number) {
  const x: (readonly [number, number])[] = [];
  const y: (readonly [number, number])[] = [];
  const total = turns * periodMs;
  for (let t = 0; t <= total; t += stepMs) {
    const angle = (2 * Math.PI * t) / periodMs;
    x.push([fromMs + t, +(amp * Math.cos(angle)).toFixed(3)]);
    y.push([fromMs + t, +(amp * Math.sin(angle)).toFixed(3)]);
  }
  x.push([fromMs + total + 200, 0]);
  y.push([fromMs + total + 200, 0]);
  return { x, y };
}

export type SketchName =
  | 'fly'
  | 'double-take'
  | 'sneeze'
  | 'yawn-stretch'
  | 'hiccups'
  | 'peekaboo'
  | 'dizzy'
  | 'doze-and-snap'
  | 'brow-groove'
  | 'suspicious';

export const SKETCHES: readonly SketchName[] = [
  'fly',
  'double-take',
  'sneeze',
  'yawn-stretch',
  'hiccups',
  'peekaboo',
  'dizzy',
  'doze-and-snap',
  'brow-groove',
  'suspicious',
];

/**
 * The catalogue. Read each one as a scene with beats — the key times ARE the
 * timing — and note that later cues on a channel simply come later in the
 * list: the rig lets the last tape with something to say win.
 */
export function sketchTapes(name: SketchName): Tape[] {
  switch (name) {
    case 'fly':
      // A fly. The eyes chase it in zigzags, the head follows, the brows
      // knit, the mouth purses with concentration — then a big blink, it is
      // gone, and a satisfied grin.
      return [
        ...look(
          [
            [200, -0.6],
            [520, -0.2],
            [780, 0.7],
            [1100, 0.4],
            [1350, -0.8],
            [1700, -0.3],
            [2000, 0.5],
            [2300, 0.9],
            [2650, 0.1],
            [2900, -0.5],
            [3200, 0],
          ],
          [
            [200, -0.5],
            [520, 0.3],
            [780, -0.2],
            [1100, 0.6],
            [1350, -0.1],
            [1700, 0.7],
            [2000, -0.6],
            [2300, 0.2],
            [2650, -0.7],
            [2900, 0.3],
            [3200, 0],
          ],
          3300
        ),
        absolute(
          'tilt',
          [
            [200, 2],
            [780, -3],
            [1350, 4],
            [2000, -4],
            [2650, 3],
            [3200, 0],
          ],
          3300,
          EASE
        ),
        ...mirrored('browRot', [[300, 6]], 3300, EASE),
        ...bothSides('browY', [[300, 0.01]], 3300, EASE),
        relative('mouthW', [[300, -0.1]], 3300, EASE),
        ...blinkAt(3300),
        relative('mouthCurve', [[3500, 0.7]], 4200, PUNCH),
        relative('mouthW', [[3500, 0.25]], 4200, PUNCH),
        ...bothSides('sy', [[3500, -0.3]], 4200, PUNCH),
        ...bothSides('browY', [[3500, -0.04]], 4200, PUNCH),
        ...bothSides('browArc', [[3500, 0.35]], 4200, PUNCH),
        ...ink([[3500, 0.5]], 4200),
      ];
    case 'double-take':
      // Looks left, casually. Looks away. SNAPS back left — eyes wide, brows
      // up, jaw down — holds it, then lets it go with a sheepish smile.
      return [
        ...look(
          [
            [0, -0.7],
            [900, 0.1],
            [1250, -0.9],
            [3000, 0],
          ],
          [
            [0, -0.1],
            [900, 0.05],
            [1250, -0.15],
            [3000, 0],
          ],
          3100
        ),
        ...bothSides('sy', [[1250, 0.3]], 2400, PUNCH),
        ...bothSides('sx', [[1250, 0.12]], 2400, PUNCH),
        ...bothSides('browY', [[1250, -0.1]], 2400, PUNCH),
        ...bothSides('browArc', [[1250, 0.6]], 2400, PUNCH),
        relative('mouthOpen', [[1250, 0.5]], 2400, PUNCH),
        relative('mouthW', [[1250, -0.25]], 2400, PUNCH),
        relative('mass', [[1250, 0.06]], 2400, PUNCH),
        ...ink([[1250, 0.5]], 2400),
        ...blinkAt(2450),
        relative('mouthCurve', [[2700, 0.45]], 3600, EASE),
        relative('mouthSkew', [[2700, 0.25]], 3600, EASE),
        ...bothSides('sy', [[2700, -0.15]], 3600, EASE),
        ...bothSides('browY', [[2700, -0.02]], 3600, EASE),
        ...mirrored('browRot', [[2700, -5]], 3600, EASE),
        ...ink([[2700, 0.4]], 3600),
      ];
    case 'sneeze':
      // Ah… ah… AH-TCHOO. The brows climb and the eyes squeeze while the
      // mouth opens by degrees, the head draws back — then the whole face
      // squashes down and forward, eyes shut, and recovers with a sniff.
      return [
        ...bothSides(
          'browY',
          [
            [200, -0.03],
            [900, -0.07],
            [1500, -0.1],
            [1900, 0.02],
          ],
          2600,
          EASE
        ),
        ...bothSides(
          'sy',
          [
            [200, -0.05],
            [900, -0.15],
            [1500, -0.25],
          ],
          2500,
          EASE
        ),
        relative(
          'mouthOpen',
          [
            [200, 0.08],
            [900, 0.18],
            [1500, 0.3],
            [1900, 0.65],
            [2400, 0.05],
          ],
          2800,
          PUNCH
        ),
        relative(
          'mouthW',
          [
            [1500, -0.1],
            [1900, 0.2],
          ],
          2800,
          PUNCH
        ),
        relative('mouthCurve', [[1900, -0.2]], 2800, PUNCH),
        relative(
          'mass',
          [
            [900, 0.03],
            [1500, 0.06],
            [1900, -0.12],
            [2200, 0.02],
          ],
          2800,
          PUNCH
        ),
        relative(
          'massY',
          [
            [1500, -0.03],
            [1900, 0.06],
          ],
          2600,
          PUNCH
        ),
        absolute(
          'tilt',
          [
            [1900, 4],
            [2300, 0],
          ],
          2800,
          PUNCH
        ),
        ...blinkAt(1900, 450),
        ...ink(
          [
            [200, 0.3],
            [1900, 0.5],
          ],
          3400
        ),
        relative('mouthW', [[2900, -0.35]], 3400, PUNCH),
        relative('mouthOpen', [[2900, 0.12]], 3400, PUNCH),
        ...blinkAt(3450),
      ];
    case 'yawn-stretch':
      // A slow, enormous yawn — brows up, eyes squeezed, the whole face
      // stretching taller — then a sleepy blink, and a shake to wake up.
      return [
        ...bothSides(
          'browY',
          [
            [0, -0.02],
            [600, -0.08],
          ],
          2400,
          HEAVY
        ),
        ...bothSides('browArc', [[600, 0.5]], 2400, HEAVY),
        relative(
          'mouthOpen',
          [
            [0, 0.1],
            [500, 0.45],
            [1000, 0.75],
            [1900, 0.7],
            [2400, 0.15],
          ],
          2700,
          HEAVY
        ),
        relative('mouthW', [[500, -0.2]], 2700, HEAVY),
        relative('mouthCurve', [[500, -0.15]], 2700, HEAVY),
        ...bothSides(
          'sy',
          [
            [600, -0.2],
            [1000, -0.55],
            [2000, -0.5],
          ],
          2700,
          HEAVY
        ),
        relative(
          'mass',
          [
            [400, 0.04],
            [1000, 0.08],
            [2000, 0.07],
          ],
          2700,
          HEAVY
        ),
        relative(
          'massY',
          [
            [400, -0.02],
            [1000, -0.05],
          ],
          2700,
          HEAVY
        ),
        absolute('tilt', [[600, -3]], 2700, HEAVY),
        ...ink([[600, 0.5]], 2700),
        ...blinkAt(2900, 500, 1, SLOW_LID),
        absolute(
          'tilt',
          [
            [3700, 4],
            [3850, -4],
            [4000, 3],
            [4150, -2],
            [4300, 0],
          ],
          4600,
          PUNCH
        ),
        ...bothSides('sy', [[3700, 0.12]], 4600, PUNCH),
        ...bothSides('browY', [[3700, -0.05]], 4600, PUNCH),
        relative('mouthCurve', [[3800, 0.3]], 4600, PUNCH),
        ...ink([[3700, 0.4]], 4600),
      ];
    case 'hiccups':
      // Three hiccups, never on the beat: the head pops, the mouth "hic"s,
      // the eyes bounce. Then the face is surprised at itself, looks to the
      // side, and settles into an embarrassed smirk.
      return [
        relative(
          'mass',
          [
            [300, 0.07],
            [420, -0.03],
            [600, 0],
            [1400, 0.07],
            [1520, -0.03],
            [1700, 0],
            [2100, 0.08],
            [2220, -0.03],
          ],
          2400,
          PUNCH
        ),
        relative(
          'massY',
          [
            [300, -0.03],
            [450, 0],
            [1400, -0.03],
            [1550, 0],
            [2100, -0.035],
          ],
          2400,
          PUNCH
        ),
        relative(
          'mouthOpen',
          [
            [300, 0.3],
            [450, 0],
            [1400, 0.3],
            [1550, 0],
            [2100, 0.35],
          ],
          2400,
          PUNCH
        ),
        relative(
          'mouthW',
          [
            [300, -0.15],
            [450, 0],
            [1400, -0.15],
            [1550, 0],
            [2100, -0.15],
          ],
          2400,
          PUNCH
        ),
        ...bothSides(
          'sy',
          [
            [300, 0.1],
            [450, 0],
            [1400, 0.1],
            [1550, 0],
            [2100, 0.12],
          ],
          2400,
          PUNCH
        ),
        absolute(
          'blinkL',
          [
            [320, 0.6],
            [420, 0],
            [1420, 0.6],
            [1520, 0],
          ],
          1800,
          LID
        ),
        absolute(
          'blinkR',
          [
            [370, 0.6],
            [470, 0],
            [1470, 0.6],
            [1570, 0],
          ],
          1850,
          LID
        ),
        ...bothSides('sy', [[2500, 0.25]], 3300, PUNCH),
        ...bothSides('browY', [[2500, -0.09]], 3300, PUNCH),
        ...bothSides('browArc', [[2500, 0.55]], 3300, PUNCH),
        relative('mouthOpen', [[2500, 0.35]], 3300, PUNCH),
        ...look(
          [
            [2500, 0.6],
            [3300, 0],
          ],
          [
            [2500, -0.3],
            [3300, 0],
          ],
          3400
        ),
        relative('mouthSkew', [[3400, 0.35]], 4000, EASE),
        relative('mouthCurve', [[3400, 0.3]], 4000, EASE),
        ...mirrored('browRot', [[3400, -6]], 4000, EASE),
        ...bothSides('sy', [[3400, -0.15]], 4000, EASE),
        ...ink(
          [
            [300, 0.4],
            [2500, 0.5],
          ],
          4000
        ),
      ];
    case 'peekaboo':
      // Eyes shut tight over a mischievous grin. One eye peeks. Then both pop
      // wide open — boo!
      return [
        absolute('blinkL', [[0, 1]], 1500, LID),
        absolute('blinkR', [[0, 1]], 2400, LID),
        ...bothSides('sy', [[0, -0.15]], 1500, PUNCH),
        relative('mouthCurve', [[100, 0.6]], 3600, PUNCH),
        relative('mouthW', [[100, 0.2]], 3600, PUNCH),
        ...bothSides('browY', [[100, -0.03]], 3600, PUNCH),
        ...bothSides('browArc', [[100, 0.3]], 3600, PUNCH),
        ...ink([[0, 0.5]], 3600),
        absolute('blinkL', [[1500, 0.35]], 2400, LID),
        relative('mouthSkew', [[1500, 0.3]], 2400, PUNCH),
        absolute(
          'blinkL',
          [
            [2400, -0.06],
            [2550, 0],
          ],
          2800,
          LID
        ),
        absolute(
          'blinkR',
          [
            [2400, -0.06],
            [2550, 0],
          ],
          2800,
          LID
        ),
        ...bothSides('sy', [[2400, 0.25]], 3300, PUNCH),
        ...bothSides('sx', [[2400, 0.1]], 3300, PUNCH),
        ...bothSides('browY', [[2400, -0.1]], 3300, PUNCH),
        ...bothSides('browArc', [[2400, 0.6]], 3300, PUNCH),
        relative('mouthOpen', [[2400, 0.3]], 3300, PUNCH),
        relative('mass', [[2400, 0.06]], 3300, PUNCH),
      ];
    case 'dizzy': {
      // The eyes roll around twice, then the head wobbles, half-lidded and
      // wavy-mouthed, until a quick shake and a blink clear it.
      const roll = circle(0, 2, 1200, 0.8, 200);
      return [
        ...look(roll.x, roll.y, 2700, EASE),
        absolute(
          'tilt',
          [
            [2600, 6],
            [2900, -6],
            [3200, 5],
            [3500, -4],
            [3800, 2],
            [4100, 0],
          ],
          4300,
          EASE
        ),
        ...bothSides('sy', [[2600, -0.3]], 4000, EASE),
        relative(
          'mouthSkew',
          [
            [2600, 0.3],
            [2900, -0.3],
            [3200, 0.25],
            [3500, -0.2],
          ],
          4000,
          EASE
        ),
        relative('mouthCurve', [[2600, -0.15]], 4000, EASE),
        relative('mouthOpen', [[2600, 0.1]], 4000, EASE),
        ...ink([[2600, 0.4]], 4600),
        absolute(
          'tilt',
          [
            [4100, -5],
            [4250, 5],
            [4400, 0],
          ],
          4600,
          PUNCH
        ),
        ...blinkAt(4300),
        ...bothSides('sy', [[4200, 0.1]], 4600, PUNCH),
      ];
    }
    case 'doze-and-snap':
      // The eyes droop by degrees, the head tips, the mouth slackens — then
      // a jolt: eyes wide, brows up, a dart left and right, and a sheepish
      // grin about it.
      return [
        ...bothSides(
          'sy',
          [
            [0, -0.1],
            [800, -0.3],
            [1600, -0.5],
            [2400, -0.65],
          ],
          2900,
          HEAVY
        ),
        ...bothSides(
          'ty',
          [
            [800, 0.02],
            [2400, 0.05],
          ],
          2900,
          HEAVY
        ),
        absolute(
          'tilt',
          [
            [600, -3],
            [2400, -7],
          ],
          2900,
          HEAVY
        ),
        relative(
          'massY',
          [
            [800, 0.01],
            [2400, 0.04],
          ],
          2900,
          HEAVY
        ),
        ...bothSides(
          'browY',
          [
            [800, 0.01],
            [2400, 0.02],
          ],
          2900,
          HEAVY
        ),
        ...mirrored('browRot', [[800, -3]], 2900, HEAVY),
        relative(
          'mouthOpen',
          [
            [1600, 0.08],
            [2400, 0.14],
          ],
          2900,
          HEAVY
        ),
        relative('mouthCurve', [[1600, -0.1]], 2900, HEAVY),
        relative('mouthW', [[1600, -0.08]], 2900, HEAVY),
        relative('mass', [[2900, 0.08]], 3600, PUNCH),
        ...bothSides('sy', [[2900, 0.3]], 3800, PUNCH),
        ...bothSides('sx', [[2900, 0.1]], 3800, PUNCH),
        ...bothSides('browY', [[2900, -0.1]], 3800, PUNCH),
        ...bothSides('browArc', [[2900, 0.6]], 3800, PUNCH),
        relative('mouthOpen', [[2900, 0.4]], 3600, PUNCH),
        relative('mouthW', [[2900, -0.2]], 3600, PUNCH),
        absolute(
          'tilt',
          [
            [2900, 3],
            [3100, 0],
          ],
          3600,
          PUNCH
        ),
        ...look(
          [
            [3000, -0.8],
            [3350, 0.8],
            [3700, 0],
          ],
          [
            [3000, -0.2],
            [3350, -0.2],
            [3700, 0],
          ],
          3900
        ),
        relative('mouthCurve', [[3900, 0.5]], 4950, EASE),
        relative('mouthSkew', [[3900, 0.2]], 4950, EASE),
        ...bothSides('sy', [[3900, -0.15]], 4950, EASE),
        ...mirrored('browRot', [[3900, -6]], 4950, EASE),
        ...blinkAt(4300),
        ...ink([[2900, 0.5]], 5000),
      ];
    case 'brow-groove':
      // A little groove: the brows take turns, the head bobs off the beat,
      // the mouth wiggles in time, the gaze sways — and it ends on both
      // brows up and a grin.
      return [
        relative(
          'browYL',
          [
            [0, -0.06],
            [300, 0],
            [600, -0.06],
            [900, 0],
            [1250, -0.06],
            [1550, 0],
            [1900, -0.06],
          ],
          2200,
          PUNCH
        ),
        relative(
          'browYR',
          [
            [300, -0.06],
            [600, 0],
            [900, -0.06],
            [1250, 0],
            [1550, -0.06],
            [1900, 0],
            [2200, -0.06],
          ],
          2500,
          PUNCH
        ),
        relative(
          'browArcL',
          [
            [0, 0.3],
            [300, 0],
            [600, 0.3],
            [900, 0],
            [1250, 0.3],
            [1550, 0],
            [1900, 0.3],
          ],
          2200,
          PUNCH
        ),
        relative(
          'browArcR',
          [
            [300, 0.3],
            [600, 0],
            [900, 0.3],
            [1250, 0],
            [1550, 0.3],
            [1900, 0],
            [2200, 0.3],
          ],
          2500,
          PUNCH
        ),
        relative(
          'massY',
          [
            [150, 0.02],
            [450, 0],
            [750, 0.02],
            [1050, 0],
            [1400, 0.02],
            [1700, 0],
            [2050, 0.02],
          ],
          2350,
          PUNCH
        ),
        relative(
          'mouthSkew',
          [
            [0, 0.25],
            [300, -0.25],
            [600, 0.25],
            [900, -0.25],
            [1250, 0.25],
            [1550, -0.25],
            [1900, 0.25],
            [2200, -0.25],
          ],
          2500,
          PUNCH
        ),
        relative('mouthCurve', [[0, 0.3]], 2800, EASE),
        ...look(
          [
            [0, -0.3],
            [600, 0.3],
            [1250, -0.3],
            [1900, 0.3],
            [2500, 0],
          ],
          [
            [0, 0.05],
            [600, 0.05],
            [1250, 0.05],
            [1900, 0.05],
            [2500, 0],
          ],
          2800,
          EASE
        ),
        ...ink([[0, 0.4]], 2800),
        ...bothSides('browY', [[2800, -0.08]], 3800, PUNCH),
        ...bothSides('browArc', [[2800, 0.5]], 3800, PUNCH),
        relative('mouthCurve', [[2800, 0.8]], 3800, PUNCH),
        relative('mouthW', [[2800, 0.3]], 3800, PUNCH),
        relative('mouthOpen', [[2800, 0.12]], 3800, PUNCH),
        ...bothSides('sy', [[2800, -0.4]], 3800, PUNCH),
        ...ink([[2800, 0.5]], 3800),
      ];
    case 'suspicious':
      // Narrowed eyes slide slowly left, then right — what are you up to? —
      // one brow up, the mouth pursed to a side, the head leaning. Then
      // "nah": brows up, a grin, a blink.
      return [
        ...bothSides(
          'sy',
          [
            [0, -0.15],
            [500, -0.45],
          ],
          3000,
          EASE
        ),
        ...mirrored('browRot', [[300, 7]], 3000, EASE),
        relative('browYL', [[500, -0.04]], 3000, EASE),
        relative('browArcL', [[500, 0.3]], 3000, EASE),
        relative('mouthW', [[400, -0.2]], 3000, EASE),
        relative('mouthSkew', [[400, -0.25]], 3000, EASE),
        ...look(
          [
            [400, -0.7],
            [1700, 0.7],
            [2900, 0],
          ],
          [
            [400, 0.1],
            [1700, 0.1],
            [2900, 0],
          ],
          3000,
          EASE
        ),
        absolute(
          'tilt',
          [
            [400, -3],
            [1700, 3],
            [2900, 0],
          ],
          3000,
          EASE
        ),
        ...ink([[300, 0.35]], 3000),
        ...bothSides('browY', [[3100, -0.07]], 4200, PUNCH),
        ...bothSides('browArc', [[3100, 0.5]], 4200, PUNCH),
        ...bothSides(
          'sy',
          [
            [3100, 0.1],
            [3500, -0.25],
          ],
          4200,
          PUNCH
        ),
        relative('mouthCurve', [[3100, 0.7]], 4200, PUNCH),
        relative('mouthW', [[3100, 0.25]], 4200, PUNCH),
        relative('mass', [[3100, 0.04]], 4200, PUNCH),
        ...blinkAt(3150),
        ...ink([[3100, 0.5]], 4200),
      ];
  }
}

/** How long a sketch runs — its longest tape. */
export function sketchDurationMs(tapes: readonly Tape[]): number {
  return Math.max(...tapes.map(tape => tape.durationMs ?? 0));
}

/** Pick a sketch uniformly from the first random number. */
export function pickSketch(random: () => number): SketchName {
  return SKETCHES[Math.min(SKETCHES.length - 1, Math.floor(random() * SKETCHES.length))];
}

/** Delay until the next sketch — uniform inside the band. */
export function drawSketchDelayMs(random: () => number): number {
  return Math.round(SKETCH_MIN_DELAY_MS + random() * (SKETCH_MAX_DELAY_MS - SKETCH_MIN_DELAY_MS));
}
