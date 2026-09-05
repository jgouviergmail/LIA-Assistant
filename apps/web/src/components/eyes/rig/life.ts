/**
 * The face's own life — cartoon mimics, at random, at a random cadence.
 *
 * The moving hold keeps a resting face from freezing, and the idle gestures
 * reach the mouth now and then, but both are SMALL by rule: a hold must stay
 * under the fidget line, and a gesture is one beat every few seconds shared
 * with the eyes. Watched for a minute on the running widget (owner,
 * 2026-09-05), the mouth was still a bar under two living eyes; a first,
 * discreet version of this library "moved a little" and was rightly called
 * neither Pixar nor expressive. This character is not a face on a video
 * call. It is a CARTOON — a little funny, and it embodies LIA — so between
 * two turns it does what a cartoon face does with nothing to do: grins at a
 * thought and squints into it, gasps "oh" at nothing, sulks for a second,
 * hums over a problem with one eye narrowed, smirks, puckers, giggles.
 *
 * Three rules make it cartoon rather than a tic, and they are all TIMING:
 *
 *  - the whole face commits. A grin squashes the eyes into arcs, a gasp
 *    widens them and flings the brows, a sulk drops the eyes' outer corners.
 *    A mouth that acts alone under two indifferent eyes is a mask;
 *  - ATTACK, HOLD, RELEASE. The pose is reached fast, with a little
 *    overshoot (the flesh), HELD long enough to be read (350 to 700 ms) and
 *    let go SLOWER than it came. The release is not a key: a scene's tape
 *    simply ENDS at its release time, the channel is handed back to the
 *    pose and eases home on the expression's own dynamics (the `base`
 *    preset settles in about 650 ms, a drowsy face slower still) — the
 *    slow-out of the animation textbooks, and it is continuous by
 *    construction (position and velocity carry across the hand-over). A
 *    first version keyed the return on the attack spring and every scene
 *    snapped shut as fast as it had opened;
 *  - it only plays with an entropy source, only on the resting expressions,
 *    and every tape returns to a relative zero: a mimic is a BEAT on top of
 *    whatever the pose is, never a new pose.
 */

import { bothSides, mirrored, relative, scaleTapes, type Keys } from '@/components/eyes/rig/choreo';
import type { ChannelKey } from '@/components/eyes/rig/channels';
import type { SpringConfig } from '@/components/eyes/rig/spring';
import type { Tape } from '@/components/eyes/rig/tape';
import type { EyeExpression } from '@/components/eyes/expression-engine';

/** The resting expressions whose face lives (the breathing set). */
export const MOUTH_LIFE_EXPRESSIONS: ReadonlySet<EyeExpression> = new Set([
  'neutral',
  'attentive',
  'tender',
  'joy',
  'bored',
  'tired',
  'thinking',
]);

/**
 * Pause between two mimics, uniformly drawn — never a beat.
 *
 * Calibrated twice. At 2.2 to 6.5 s with bursts at 0.9 s, on top of the eye
 * gestures the idle life already plays every 1.9 to 5.6 s (a third of them
 * reaching the face), the face did something every two seconds and the
 * owner read it as nervous tics. The standard for a resting character is a
 * facial beat every eight to twelve seconds, with the eyes wandering in
 * between: six to fourteen seconds here, a mean near nine, and the rare
 * follow-up spaced by nearly two seconds instead of one.
 */
export const MOUTH_LIFE_MIN_DELAY_MS = 6000;
export const MOUTH_LIFE_MAX_DELAY_MS = 14000;

/** Chance that a mimic is followed by another sooner (a thought unfolding —
 * rare, or the follow-ups become the cadence). */
export const MOUTH_LIFE_BURST_PROBABILITY = 0.1;
export const MOUTH_LIFE_BURST_DELAY_MS = 1800;

/** Size drawn for each performance, on the relative travel. */
export const MOUTH_LIFE_SCALE_MIN = 0.8;
export const MOUTH_LIFE_SCALE_SPAN = 0.4;

/** The longest a scene HOLDS before it is handed back — a beat, never a
 * state (the eased return afterwards is the expression's own). */
export const MOUTH_LIFE_MAX_MS = 1200;

/**
 * ATTACK springs — and only the attack. A tape ends at its release, so the
 * way OUT of every scene is the expression's own dynamics (see the class
 * comment): these springs shape how a shape is reached, never how it lets
 * go. Quick, with a discreet overshoot: at 0.55 of damping the first
 * version rang, and a ring on a face reads as a twitch.
 */
const SNAP: SpringConfig = { frequency: 3.8, damping: 0.72 };
/** A softer attack for the sulks and the hums. */
const SETTLE: SpringConfig = { frequency: 2.6, damping: 0.85 };
/** Quicker, for a wiggle and a smack — the small beats. */
const FLICK: SpringConfig = { frequency: 5, damping: 0.85 };

/** A relative beat on one channel — the shared vocabulary of `choreo.ts`. */
function beat(channel: ChannelKey, keys: Keys, durationMs: number, spring: SpringConfig): Tape {
  return relative(channel, keys, durationMs, spring);
}

/** The same beat on both sides, the right one trailing and a hair smaller. */
function both(
  base: 'browY' | 'browArc' | 'sy' | 'sx' | 'ty',
  keys: Keys,
  durationMs: number,
  spring: SpringConfig
): Tape[] {
  return bothSides(base, keys, durationMs, spring);
}

export type MouthMimic =
  | 'grin'
  | 'gasp'
  | 'sulk'
  | 'hmm'
  | 'smirk'
  | 'pucker'
  | 'giggle'
  | 'wiggle'
  | 'smack';

/**
 * The library, with the weight of each draw. The big scenes (a grin, a gasp,
 * a sulk, a giggle, a pucker) are rarer than the small ones: a face that
 * gasps every ten seconds is not a character, it is a slot machine.
 */
export const MOUTH_MIMIC_WEIGHTS: readonly (readonly [MouthMimic, number])[] = [
  ['grin', 0.14],
  ['gasp', 0.07],
  ['sulk', 0.1],
  ['giggle', 0.08],
  ['pucker', 0.07],
  ['hmm', 0.16],
  ['smirk', 0.16],
  ['wiggle', 0.12],
  ['smack', 0.1],
];

export const MOUTH_MIMICS: readonly MouthMimic[] = MOUTH_MIMIC_WEIGHTS.map(([mimic]) => mimic);

/**
 * How much a scene INKS the mouth and the brows while it plays.
 *
 * At rest both organs sit at half presence (a quiet face), and a mimic that
 * moved them at half ink read as washed out next to two solid eyes — seen
 * on the frozen strip, not guessed. A cartoon face that performs commits in
 * full: the big scenes go to full ink, the small ones part of the way, on
 * the scene's own attack / hold / release, derived from its lead mouth tape
 * so the ink can never outlive or lag the shape it belongs to.
 */
const MIMIC_INK: Record<MouthMimic, number> = {
  grin: 0.5,
  gasp: 0.5,
  sulk: 0.5,
  giggle: 0.5,
  pucker: 0.5,
  hmm: 0.45,
  smirk: 0.45,
  wiggle: 0.3,
  smack: 0.25,
};

/** The ink tapes of a scene: presence of the mouth and both brows, keyed on
 * the scene's own lead mouth tape (its first key is the attack, its last
 * zero the release) and lasting as long as the longest tape does. */
function inkTapes(scene: readonly Tape[], amount: number): Tape[] {
  const lead = scene.find(tape => tape.channel.startsWith('mouth')) ?? scene[0];
  const attackMs = lead.keys[0].atMs;
  const releaseMs = Math.max(...scene.map(tape => tape.durationMs ?? 0));
  const keys = [[attackMs, amount]] as const;
  return [
    beat('mouthA', keys, releaseMs, SNAP),
    beat('browAL', keys, releaseMs, SNAP),
    beat('browAR', keys, releaseMs, SNAP),
  ];
}

/**
 * The tapes of one mimic. `side` is +1 or -1 and picks which corner leads on
 * the asymmetric ones; the caller scales the result for the occasion. Every
 * scene is written as attack / hold / release — read the key times — and
 * carries its own ink.
 */
export function mimicTapes(mimic: MouthMimic, side: 1 | -1): Tape[] {
  const scene = SCENES[mimic](side);
  return [...scene, ...inkTapes(scene, MIMIC_INK[mimic])];
}

/**
 * One builder per scene — a table rather than a switch, so no single
 * function carries nine scenes and their side ternaries (the complexity
 * ratchet counted 16 on the switch; each builder here is a handful).
 */
const SCENES: Record<MouthMimic, (side: 1 | -1) => Tape[]> = {
  // The big cheesy smile: a tiny pull-in first (anticipation), then the
  // corners fly, the mouth spreads and parts, the eyes squash into happy
  // arcs, the brows lift — held, then let go.
  grin: side => [
    beat(
      'mouthW',
      [
        [0, -0.06],
        [90, 0.35],
      ],
      640,
      SNAP
    ),
    beat('mouthCurve', [[90, 0.85]], 640, SNAP),
    beat('mouthOpen', [[110, 0.14]], 600, SNAP),
    beat('mouthSkew', [[120, 0.12 * side]], 640, SNAP),
    ...both('sy', [[100, -0.42]], 640, SNAP),
    ...both('ty', [[100, -0.05]], 640, SNAP),
    ...both('browY', [[80, -0.05]], 640, SNAP),
    ...both('browArc', [[80, 0.4]], 640, SNAP),
  ],
  // "Oh!" — the jaw drops to an O, the eyes go wide, the brows fly, the
  // whole head pops a hair. Held a beat, then it closes.
  gasp: () => [
    beat('mouthOpen', [[0, 0.6]], 520, SNAP),
    beat('mouthW', [[0, -0.28]], 520, SNAP),
    beat('mouthCurve', [[0, -0.1]], 520, SNAP),
    ...both('sy', [[0, 0.22]], 520, SNAP),
    ...both('sx', [[0, 0.1]], 520, SNAP),
    ...both('browY', [[0, -0.1]], 520, SNAP),
    ...both('browArc', [[0, 0.6]], 520, SNAP),
    {
      channel: 'mass',
      keys: [{ atMs: 0, value: 0.05 }],
      durationMs: 520,
      spring: SNAP,
      relative: true,
    },
  ],
  // The cartoon sulk: corners way down, mouth pulled in and pushed low,
  // the eyes' outer corners droop, the inner brows climb. Held longest.
  sulk: () => [
    beat('mouthCurve', [[0, -0.65]], 700, SETTLE),
    beat('mouthW', [[0, -0.16]], 700, SETTLE),
    beat('mouthY', [[0, 0.025]], 700, SETTLE),
    ...mirrored('rot', [[40, -5]], 700, SETTLE),
    ...mirrored('browRot', [[40, -9]], 700, SETTLE),
    ...both('browY', [[40, 0.015]], 700, SETTLE),
    ...both('sy', [[40, -0.12]], 700, SETTLE),
  ],
  // Working on something: the lips purse to a knot on one side, one eye
  // narrows, one brow goes up, the head tips. The thinking face, held.
  hmm: side => [
    beat('mouthW', [[0, -0.3]], 640, SETTLE),
    beat('mouthOpen', [[0, 0.09]], 640, SETTLE),
    beat('mouthSkew', [[0, 0.22 * side]], 640, SETTLE),
    beat(side === 1 ? 'syR' : 'syL', [[40, -0.28]], 640, SETTLE),
    beat(side === 1 ? 'browYL' : 'browYR', [[40, -0.05]], 640, SETTLE),
    beat(side === 1 ? 'browArcL' : 'browArcR', [[40, 0.35]], 640, SETTLE),
    beat('tilt', [[0, 2.6 * side]], 640, SETTLE),
  ],
  // One corner up and HELD, the brow above it up, the OTHER eye half
  // closed — the face that knows something.
  smirk: side => [
    beat('mouthSkew', [[0, 0.42 * side]], 620, SNAP),
    beat('mouthCurve', [[40, 0.3]], 620, SNAP),
    beat(side === 1 ? 'browArcL' : 'browArcR', [[60, 0.35]], 620, SNAP),
    beat(side === 1 ? 'browYL' : 'browYR', [[60, -0.04]], 620, SNAP),
    beat(side === 1 ? 'syR' : 'syL', [[60, -0.2]], 620, SNAP),
  ],
  // A kiss at nothing: the mouth gathers to a small open knot pushed
  // forward and down, the eyes soften, the brows lift a touch.
  pucker: () => [
    beat('mouthW', [[0, -0.45]], 520, SNAP),
    beat('mouthOpen', [[0, 0.15]], 520, SNAP),
    beat('mouthY', [[0, 0.03]], 520, SNAP),
    beat('mouthCurve', [[0, 0.1]], 520, SNAP),
    ...both('sy', [[0, -0.16]], 520, SNAP),
    ...both('browArc', [[0, 0.22]], 520, SNAP),
  ],
  // A giggle: two quick bounces of the whole head, the mouth grinning
  // and the eyes squashed shut-ish on each, brows up.
  giggle: () => [
    {
      channel: 'mass',
      keys: [
        { atMs: 0, value: 0.04 },
        { atMs: 180, value: -0.02 },
        { atMs: 360, value: 0.035 },
      ],
      durationMs: 560,
      spring: SNAP,
      relative: true,
    },
    beat('mouthCurve', [[0, 0.6]], 560, SNAP),
    beat('mouthW', [[0, 0.2]], 560, SNAP),
    beat(
      'mouthOpen',
      [
        [0, 0.16],
        [180, 0.04],
        [360, 0.14],
      ],
      560,
      SNAP
    ),
    ...both(
      'sy',
      [
        [0, -0.3],
        [180, -0.15],
        [360, -0.3],
      ],
      560,
      SNAP
    ),
    ...both('browY', [[0, -0.04]], 560, SNAP),
    ...both('browArc', [[0, 0.3]], 560, SNAP),
  ],
  // The mouth wiggles side to side, three times, while the eyes stay put
  // — the cartoon "hmm, hmm, hmm".
  wiggle: side => [
    beat(
      'mouthSkew',
      [
        [0, 0.28 * side],
        [170, -0.26 * side],
        [340, 0.22 * side],
      ],
      520,
      FLICK
    ),
    beat(
      'mouthW',
      [
        [0, -0.08],
        [170, 0.06],
        [340, -0.06],
      ],
      520,
      FLICK
    ),
    beat('mouthCurve', [[0, 0.12]], 520, FLICK),
  ],
  // A double smack of the lips, with the brows flicking once — a tut.
  smack: () => [
    beat(
      'mouthOpen',
      [
        [0, 0.14],
        [120, 0],
        [220, 0.12],
      ],
      340,
      FLICK
    ),
    beat('mouthW', [[0, -0.1]], 340, FLICK),
    ...both('browY', [[0, -0.025]], 300, FLICK),
  ],
};

/** Scale the relative travel of a performance for the occasion. Every tape
 * of a mimic is relative, so the whole scene scales. */
export function scaleMimic(tapes: readonly Tape[], scale: number): Tape[] {
  return scaleTapes(tapes, scale, false);
}

/** One drawn performance: which mimic, which side, what size. */
export interface MouthLifeDraw {
  readonly mimic: MouthMimic;
  readonly tapes: Tape[];
}

/** Pick a mimic from the weights — the first random number decides. */
export function pickMimic(random: () => number): MouthMimic {
  const total = MOUTH_MIMIC_WEIGHTS.reduce((sum, [, weight]) => sum + weight, 0);
  let cursor = random() * total;
  for (const [mimic, weight] of MOUTH_MIMIC_WEIGHTS) {
    cursor -= weight;
    if (cursor < 0) return mimic;
  }
  return MOUTH_MIMIC_WEIGHTS[MOUTH_MIMIC_WEIGHTS.length - 1][0];
}

/**
 * Draw the next mimic from the entropy source: weighted over the library, a
 * random side for the asymmetric ones, a random size. Pure given `random`.
 */
export function drawMouthMimic(random: () => number): MouthLifeDraw {
  const mimic = pickMimic(random);
  const side: 1 | -1 = random() < 0.5 ? 1 : -1;
  const scale = MOUTH_LIFE_SCALE_MIN + random() * MOUTH_LIFE_SCALE_SPAN;
  return { mimic, tapes: scaleMimic(mimicTapes(mimic, side), scale) };
}

/**
 * A small deterministic generator (xorshift32) for the life's OWN stream.
 *
 * The rig's `random` option feeds the arrival pace, and the widget tests pin
 * `Math.random` with exact once-sequences read at mount in a known order
 * (blink delay, idle delay, then each tick's rolls). A life drawing from that
 * same stream at construction shifts every one of those sequences by one and
 * fails four tests three files away. The life therefore draws from a stream
 * the host seeds once per mount, and never from `Math.random`.
 */
export function createLifeRandom(seed: number): () => number {
  let state = seed >>> 0 || 0x9e3779b9;
  return () => {
    state ^= state << 13;
    state >>>= 0;
    state ^= state >>> 17;
    state ^= state << 5;
    state >>>= 0;
    return state / 0x100000000;
  };
}

/** Delay until the next mimic — uniform, with the occasional quick follow-up. */
export function drawMouthLifeDelayMs(random: () => number): number {
  if (random() < MOUTH_LIFE_BURST_PROBABILITY) return MOUTH_LIFE_BURST_DELAY_MS;
  return Math.round(
    MOUTH_LIFE_MIN_DELAY_MS + random() * (MOUTH_LIFE_MAX_DELAY_MS - MOUTH_LIFE_MIN_DELAY_MS)
  );
}
