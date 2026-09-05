/**
 * Scripts — what an emotion DOES on the way in, and what a state keeps doing.
 *
 * Two kinds, both expressed as tapes:
 *
 *  - ARRIVALS: the little entrance an emotion makes. Springs alone give every
 *    expression the same choreography — a counter-move, then a glide — and a
 *    face where anger and tenderness arrive the same way is a face reciting
 *    labels. Anger takes a breath and SLAMS; sadness deflates; a question
 *    tilts its head. Each is a handful of keys, and it is the difference
 *    between an interface changing state and a character reacting.
 *
 *  - PATTERNS: looping behaviour a state keeps up for as long as it lasts.
 *    Searching is the one that matters: a smooth left-right sweep is what a
 *    security camera does. Eyes that look for something make SACCADES — a
 *    quick jump, a brief fixation, another jump, to scattered places, never on
 *    a beat. That is what the pattern below describes.
 *
 * Patterns are owned by the expression and are dropped when it changes;
 * arrivals play once and hand their channels back.
 */

import {
  absolute as absoluteBeat,
  bothSides,
  relative,
  type Keys,
} from '@/components/eyes/rig/choreo';
import type { Tape, TapeKey } from '@/components/eyes/rig/tape';
import type { SpringConfig } from '@/components/eyes/rig/spring';
import type { EyeExpression } from '@/components/eyes/expression-engine';

/** A saccade is the fastest thing an eye does: it JUMPS, it does not travel. */
const SACCADE_SPRING: SpringConfig = { frequency: 6.5, damping: 1 };

/** Fixations, in ms from the start of the search. Deliberately irregular:
 * evenly spaced jumps read as a machine stepping through a list. */
const SEARCH_BEATS = [0, 340, 620, 900, 1180, 1520, 1840, 2200] as const;

/** Where each fixation lands. Scattered, wider than tall (a face searching a
 * page sweeps across more than it does up and down), and it never repeats a
 * position twice in a row. */
const SEARCH_X = [-0.55, 0.62, 0.18, -0.3, 0.8, -0.72, 0.35, -0.15] as const;
const SEARCH_Y = [0.15, -0.22, 0.3, -0.05, 0.2, -0.28, 0.12, -0.18] as const;

/** The whole search cycle, after which the pattern wraps. */
const SEARCH_CYCLE_MS = 2560;

function searchTape(channel: 'gazeX' | 'gazeY', values: readonly number[]): Tape {
  return {
    channel,
    keys: SEARCH_BEATS.map((atMs, index) => ({ atMs, value: values[index] })),
    durationMs: SEARCH_CYCLE_MS,
    spring: SACCADE_SPRING,
  };
}

/**
 * The brows punctuate speech.
 *
 * A talking face raises its brows on the stresses, not on a beat: four raises
 * over a cycle no two of which are the same distance apart, each held for
 * about a syllable, both brows with the right one trailing. Between two
 * raises the tape hands the brow back to the pose (a relative 0), so a brow
 * beat from elsewhere — a gesture, an accent — still wins over it.
 */
const SPEECH_BROW_RAISES = [400, 1900, 2700, 4300] as const;
const SPEECH_BROW_HOLD_MS = 260;
const SPEECH_CYCLE_MS = 5200;
const SPEECH_BROW_LIFT_EM = -0.035;
const SPEECH_BROW_ARCH = 0.22;
const SPEECH_BROW_SPRING: SpringConfig = { frequency: 3.4, damping: 0.6 };

function speechBrowKeys(value: number, delayMs: number): TapeKey[] {
  return SPEECH_BROW_RAISES.flatMap(at => [
    { atMs: at + delayMs, value },
    { atMs: at + delayMs + SPEECH_BROW_HOLD_MS, value: 0 },
  ]);
}

function speechBrowTape(channel: Tape['channel'], value: number, delayMs: number): Tape {
  return {
    channel,
    keys: speechBrowKeys(value, delayMs),
    durationMs: SPEECH_CYCLE_MS,
    spring: SPEECH_BROW_SPRING,
    relative: true,
  };
}

function speechBrowTapes(): Tape[] {
  const trail = 40;
  const right = 0.92;
  return [
    speechBrowTape('browYL', SPEECH_BROW_LIFT_EM, 0),
    speechBrowTape('browYR', SPEECH_BROW_LIFT_EM * right, trail),
    speechBrowTape('browArcL', SPEECH_BROW_ARCH, 0),
    speechBrowTape('browArcR', SPEECH_BROW_ARCH * right, trail),
  ];
}

/**
 * Looping behaviour for a state, or nothing.
 *
 * The rig owns these for exactly as long as the expression lasts: they are
 * re-resolved on every pose change, so a search pattern can never outlive the
 * search, and the speech brows stop with the speech.
 */
export function resolvePatterns(expression: EyeExpression): readonly Tape[] {
  switch (expression) {
    case 'searching':
      return [searchTape('gazeX', SEARCH_X), searchTape('gazeY', SEARCH_Y)];
    case 'speaking':
      return speechBrowTapes();
    default:
      return [];
  }
}

/** A relative beat on one channel — an offset from wherever the pose sits
 * (the shared vocabulary of `choreo.ts`). */
function beat(
  channel: Tape['channel'],
  keys: Keys,
  durationMs: number,
  spring?: SpringConfig
): Tape {
  return relative(channel, keys, durationMs, spring);
}

/** Both brows raised or lowered, the right one trailing a hair. */
function brows(keys: Keys, durationMs: number, spring?: SpringConfig): Tape[] {
  return bothSides('browY', keys, durationMs, spring);
}

/** Both brows arched or flattened. */
function arches(keys: Keys, durationMs: number, spring?: SpringConfig): Tape[] {
  return bothSides('browArc', keys, durationMs, spring);
}

/** A yawn opens slower than a startle and closes on its own weight. */
const YAWN: SpringConfig = { frequency: 2.4, damping: 1 };

/** An absolute beat — for channels whose rest value IS the reference (the
 * mass, the head tilt). */
function absolute(
  channel: Tape['channel'],
  keys: Keys,
  durationMs: number,
  spring?: SpringConfig
): Tape {
  return absoluteBeat(channel, keys, durationMs, spring);
}

const SNAP: SpringConfig = { frequency: 5, damping: 0.9 };
const SWELL: SpringConfig = { frequency: 1.6, damping: 1.1 };
/** A mouth is light and quick: it rings more than the head does. */
const GRIN: SpringConfig = { frequency: 3.4, damping: 0.45 };

/**
 * The entrance each emotion makes.
 *
 * Read them as beats, not as numbers: anger inhales then slams, fear recoils,
 * sadness deflates, a question tips its head, a thought leans the other way.
 */
export const ARRIVAL_SCRIPTS: Partial<Record<EyeExpression, readonly Tape[]>> = {
  /** Squash down, spring past, settle — the classic joy pop. */
  joy: [
    absolute(
      'mass',
      [
        [0, 0.94],
        [150, 1.06],
      ],
      330
    ),
    ...brows([[60, -0.03]], 420),
    ...arches(
      [
        [60, 0.2],
        [230, 0],
      ],
      420,
      GRIN
    ),
    // The smile SNAPS past its own target and settles back into it. A
    // mouth that merely arrives at a curve is a diagram of a smile.
    beat(
      'mouthCurve',
      [
        [0, 0.28],
        [190, 0],
      ],
      460,
      GRIN
    ),
  ],

  /** The startle: everything gets bigger, fast, brows first. */
  surprise: [
    absolute(
      'mass',
      [
        [0, 0.92],
        [110, 1.1],
      ],
      290,
      SNAP
    ),
    ...brows([[0, -0.04]], 320, SNAP),
    // The arch flies past its pose before anything else has moved: the
    // brows are the first thing a startle does.
    ...arches(
      [
        [0, 0.3],
        [120, 0],
      ],
      320,
      SNAP
    ),
    // The jaw drops: it overshoots the open pose, then closes onto it.
    absolute(
      'mouthOpen',
      [
        [0, 0.25],
        [90, 0.95],
      ],
      300,
      SNAP
    ),
  ],

  excited: [
    absolute('mass', [[0, 1.07]], 220),
    ...brows([[0, -0.03]], 300),
    ...arches(
      [
        [0, 0.25],
        [180, 0],
      ],
      400,
      GRIN
    ),
    beat(
      'mouthCurve',
      [
        [0, 0.32],
        [180, 0],
      ],
      440,
      GRIN
    ),
    absolute(
      'mouthOpen',
      [
        [0, 0.52],
        [150, 0.38],
      ],
      380,
      GRIN
    ),
  ],

  /**
   * Anger takes a breath before it strikes. The eyes lift a hair, the brows
   * rise — and then the whole face comes down at once. Without the inhale the
   * scowl simply appears, which reads as a state change rather than as temper.
   */
  anger: [
    absolute(
      'mass',
      [
        [0, 1.05],
        [110, 0.97],
      ],
      340,
      SNAP
    ),
    ...brows(
      [
        [0, -0.05],
        [110, 0.015],
      ],
      380,
      SNAP
    ),
    // The jaw sets: the mouth pulls in tight before it settles wide.
    beat(
      'mouthW',
      [
        [0, -0.14],
        [130, 0],
      ],
      340,
      SNAP
    ),
  ],

  /** Fear recoils: it pulls back and shrinks away from what it saw. */
  fear: [
    absolute(
      'mass',
      [
        [0, 1.02],
        [90, 0.96],
      ],
      380,
      SNAP
    ),
    absolute(
      'massY',
      [
        [0, -0.02],
        [90, 0.012],
      ],
      420,
      SNAP
    ),
    beat('mouthW', [[0, -0.12]], 380, SNAP),
  ],

  /** Sadness does not arrive: it deflates. The mass sinks slowly and stays
   * low a moment longer than the lids do. */
  sad: [
    absolute(
      'mass',
      [
        [0, 1],
        [280, 0.975],
      ],
      900,
      SWELL
    ),
    absolute('massY', [[220, 0.022]], 950, SWELL),
    // The frown deepens AFTER the eyes have fallen. Grief is sequential;
    // everything landing together is a mask being swapped.
    beat('mouthCurve', [[220, -0.14]], 900, SWELL),
    // ...and the brows sink last of all, with the frown.
    ...brows([[240, 0.02]], 900, SWELL),
  ],

  /** Tenderness swells rather than lands. */
  tender: [
    absolute('mass', [[0, 1.025]], 620, SWELL),
    beat('mouthCurve', [[0, 0.1]], 620, SWELL),
    ...arches([[0, 0.12]], 620, SWELL),
  ],

  /** The quizzical head tilt — the single most legible "oh?" a face owns, and
   * it costs one channel. */
  question: [
    absolute(
      'tilt',
      [
        [0, 0.6],
        [90, 3.4],
      ],
      760,
      { frequency: 2.2, damping: 0.62 }
    ),
    // The corner lifts a beat after the head does — the smirk is the
    // punctuation, and punctuation comes last.
    beat('mouthSkew', [[70, 0.16]], 620, GRIN),
    // The ONE raised brow overshoots — the other stays put, or the question
    // becomes a surprise.
    beat(
      'browYL',
      [
        [70, -0.03],
        [300, 0],
      ],
      520,
      { frequency: 2.6, damping: 0.6 }
    ),
  ],

  /** A thought leans the other way, and slower. */
  thinking: [
    absolute('tilt', [[0, -2.4]], 900, SWELL),
    beat('mouthSkew', [[120, 0.12]], 800, SWELL),
  ],

  /** Attention perks up. */
  attentive: [absolute('mass', [[0, 1.04]], 240)],

  /** Tiredness arrives on a yawn: the mouth opens wide and closes on its own
   * weight, the inner brows lifting with it. The pose itself has a closed
   * mouth — the yawn is the entrance, not the state. */
  tired: [
    absolute(
      'mouthOpen',
      [
        [120, 0.55],
        [620, 0.02],
      ],
      900,
      YAWN
    ),
    ...brows(
      [
        [120, -0.03],
        [620, 0],
      ],
      900,
      YAWN
    ),
  ],

  /** Searching leans in before it starts looking. */
  searching: [absolute('massY', [[0, -0.015]], 420, SNAP)],

  /** A wink is a joke, and a joke needs a crooked mouth to land. */
  wink: [
    beat(
      'mouthCurve',
      [
        [0, 0.25],
        [170, 0],
      ],
      420,
      GRIN
    ),
    beat('mouthSkew', [[0, 0.14]], 460, GRIN),
  ],
};
