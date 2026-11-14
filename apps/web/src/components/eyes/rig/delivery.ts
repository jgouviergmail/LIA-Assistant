/**
 * The delivery of an answer, as tapes — what the face does when it hands an
 * answer over (ADR-294, follow-up of 2026-11-13).
 *
 * Until then a delivered answer landed on a face that did nothing: 94 % of
 * the answers measured carry no accent, and a factual one even put the
 * character's smile out. Chosen by the owner on the bench among three
 * proposals (« la remise présentée »), each delivery is now one performance:
 *
 *  1. the eyes go to the answer and, for a character with hands, an open
 *     hand presents it — then the eyes come back to the person;
 *  2. the register's own « voilà », in one of five manners (calm, sure,
 *     careful, warm, soft: `tone.ts` maps every register to one);
 *  3. later, the hand-over — « à toi » (`listenTapes`): the face leans in a
 *     little and waits, played by the host when nobody has started writing.
 *
 * Measured on the sculpted characters, and the reason for the shapes below:
 * a pitch of a few degrees of a flat painting is invisible, so a nod is the
 * HEAD dipping (`massY`) with the eyes going with it (`gazeY`) and the body
 * taking the weight (`bodySy`); a lower lid alone only crops the transparent
 * margin of a sculpted eye, so an eye smiles by its squash (`sy`, anchored
 * high by `oy`, as `excited` does); and two lids 60-70 ms apart read as a
 * wink on a recording, so a delivery's blink closes both within 18 ms.
 */

import {
  isPresentationGesture,
  type IdleGesture,
  type PresentationGesture,
} from '@/components/eyes/expression-engine';
import { absolute, bothSides, mirrored, relative, type Keys } from '@/components/eyes/rig/choreo';
import type { SpringConfig } from '@/components/eyes/rig/spring';
import type { Tape } from '@/components/eyes/rig/tape';

const BLINK: SpringConfig = { frequency: 6.2, damping: 0.72 };
const SOFT_BLINK: SpringConfig = { frequency: 4.4, damping: 0.86 };
const ACCENT: SpringConfig = { frequency: 3.8, damping: 1 };
const CRISP: SpringConfig = { frequency: 5, damping: 0.82 };
const SOFT: SpringConfig = { frequency: 3, damping: 0.95 };
const SETTLE: SpringConfig = { frequency: 2.3, damping: 0.96 };
const BOUNCE: SpringConfig = { frequency: 4.4, damping: 0.5 };
const HAND: SpringConfig = { frequency: 3.2, damping: 0.88 };

/** The two lids of a delivery close within this much of each other. */
const BLINK_PAIR_TRAIL_MS = 18;
/** When, in a presentation, the register's own « voilà » starts: the eyes
 * are on their way back from the answer and the hand is open. */
const MANNER_AT_MS = 760;

const shift = (keys: Keys, atMs: number): Keys =>
  keys.map(([time, value]) => [time + atMs, value] as const);

/** One blink of both eyes, nearly together. */
function blink(atMs: number, reopenMs = 110, spring = BLINK): Tape[] {
  return [
    absolute(
      'blinkL',
      [
        [atMs, 1],
        [atMs + reopenMs, 0],
      ],
      atMs + reopenMs + 180,
      spring
    ),
    absolute(
      'blinkR',
      [
        [atMs + BLINK_PAIR_TRAIL_MS, 1],
        [atMs + BLINK_PAIR_TRAIL_MS + reopenMs, 0],
      ],
      atMs + reopenMs + 200,
      spring
    ),
  ];
}

/** The beat of a nod: a small lift, the dip, a short hold, the return. */
const NOD_BEAT: Keys = [
  [0, 0],
  [130, -0.25],
  [310, 1],
  [540, 0.85],
  [800, 0],
];
const NOD_SETTLE: Keys = [
  [0, 0],
  [310, -0.018],
  [560, 0.006],
  [800, 0],
];

/** A nod that reads on every character; `depth` 1 is a clear « oui ». */
export function nodTapes(atMs = 0, depth = 1, spring: SpringConfig = ACCENT): Tape[] {
  const scaled = (keys: Keys, size: number): Keys =>
    shift(
      keys.map(([time, value]) => [time, value * size * depth] as const),
      atMs
    );
  return [
    relative('massY', scaled(NOD_BEAT, 0.055), atMs + 1100, spring),
    relative('headPitch', scaled(NOD_BEAT, 0.4), atMs + 1100, spring),
    relative('gazeY', scaled(NOD_BEAT, 0.3), atMs + 1100, spring),
    relative('bodySy', scaled(NOD_SETTLE, 1), atMs + 1100, spring),
  ];
}

/** The eyes smile with the mouth: the eye flattens, anchored high. */
function warmth(atMs: number, curve: number, squint: number, holdMs: number): Tape[] {
  const fade = (start: number, end: number): Keys => [
    [atMs, start],
    [atMs + holdMs, end],
  ];
  const eye = (start: number, end: number): Keys => [
    [atMs + 60, start],
    [atMs + holdMs, end],
  ];
  return [
    relative('mouthCurve', fade(curve, curve * 0.65), atMs + holdMs + 600, SOFT),
    relative('mouthW', fade(curve * 0.4, curve * 0.25), atMs + holdMs + 600, SOFT),
    ...bothSides('sy', eye(-squint, -squint * 0.6), atMs + holdMs + 650, SOFT),
    ...bothSides('oy', eye(-squint * 80, -squint * 48), atMs + holdMs + 650, SOFT),
  ];
}

/** One exhale: the body lets its weight down a hair — the job is done. */
function exhale(atMs: number): Tape[] {
  return [
    relative(
      'bodySy',
      [
        [atMs, -0.022],
        [atMs + 700, 0],
      ],
      atMs + 1100,
      SETTLE
    ),
    relative(
      'bodySx',
      [
        [atMs, 0.012],
        [atMs + 700, 0],
      ],
      atMs + 1100,
      SETTLE
    ),
  ];
}

/** « Voilà. » Back to the person on a blink, a clear nod, a kind smile, an exhale. */
function factual(at: number): Tape[] {
  return [
    ...blink(at),
    ...bothSides(
      'browY',
      [
        [at + 60, -0.03],
        [at + 420, -0.02],
        [at + 900, 0],
      ],
      at + 1100,
      SOFT
    ),
    ...nodTapes(at + 260),
    ...warmth(at + 300, 0.13, 0.2, 1600),
    ...exhale(at + 1000),
  ];
}

/** « C'est fait. » One brow flashes, a crisp nod, the chin up, a sure smile. */
function assured(at: number): Tape[] {
  const flash = (value: number): Keys => [
    [at + 70, value],
    [at + 480, 0],
  ];
  return [
    ...blink(at),
    relative('browYR', flash(-0.07), at + 760, CRISP),
    relative('browArcR', flash(0.5), at + 760, CRISP),
    ...nodTapes(at + 200, 1.1, CRISP),
    relative(
      'massY',
      [
        [at + 1050, -0.022],
        [at + 1700, -0.012],
      ],
      at + 2200,
      SOFT
    ),
    relative(
      'mouthSkew',
      [
        [at + 300, 0.12],
        [at + 1500, 0.06],
      ],
      at + 2000,
      SOFT
    ),
    ...warmth(at + 300, 0.1, 0.12, 1400),
  ];
}

/** « Voilà, avec prudence. » A slow blink, the head inclines, the inner brows
 * lift, a small one-sided smile, one slow nod of agreement at the end. */
function careful(at: number): Tape[] {
  return [
    ...blink(at, 230, SOFT_BLINK),
    relative(
      'tilt',
      [
        [at + 80, 0],
        [at + 520, 5],
        [at + 1450, 5],
        [at + 2000, 1],
      ],
      at + 2500,
      SOFT
    ),
    ...mirrored(
      'browRot',
      [
        [at + 150, -7],
        [at + 1600, -4],
      ],
      at + 2300,
      SOFT
    ),
    ...bothSides(
      'browY',
      [
        [at + 150, -0.025],
        [at + 1600, -0.015],
      ],
      at + 2300,
      SOFT
    ),
    relative(
      'mouthSkew',
      [
        [at + 300, 0.16],
        [at + 1700, 0.08],
      ],
      at + 2400,
      SOFT
    ),
    relative(
      'mouthCurve',
      [
        [at + 300, 0.06],
        [at + 1700, 0.04],
      ],
      at + 2400,
      SOFT
    ),
    ...nodTapes(at + 1250, 0.6, SOFT),
  ];
}

/** Warm, playful, celebratory: a little hop with its squash, and a smile up
 * to the eyes. */
function warm(at: number): Tape[] {
  const hop = (keys: Keys): Keys => shift(keys, at);
  return [
    ...blink(at),
    relative(
      'bodySy',
      hop([
        [0, -0.06],
        [170, 0.07],
        [390, -0.03],
        [640, 0],
      ]),
      at + 950,
      BOUNCE
    ),
    relative(
      'bodySx',
      hop([
        [0, 0.045],
        [170, -0.045],
        [390, 0.02],
        [640, 0],
      ]),
      at + 950,
      BOUNCE
    ),
    relative(
      'bodyY',
      hop([
        [0, 0.015],
        [180, -0.14],
        [410, 0.02],
        [660, 0],
      ]),
      at + 1000,
      BOUNCE
    ),
    ...warmth(at + 150, 0.16, 0.26, 1600),
  ];
}

/** Sorry, concerned or weary: a slow blink, a small bow, soft brows. */
function soft(at: number): Tape[] {
  return [
    ...blink(at, 380, SOFT_BLINK),
    ...nodTapes(at + 150, 0.8, SOFT),
    ...mirrored(
      'browRot',
      [
        [at + 150, -8],
        [at + 1500, -5],
      ],
      at + 2200,
      SOFT
    ),
  ];
}

const MANNERS: Record<PresentationGesture, (at: number) => Tape[]> = {
  'present-factual': factual,
  'present-assured': assured,
  'present-careful': careful,
  'present-warm': warm,
  'present-soft': soft,
};

/** A presentation: the look at the answer and the open hand that presents
 * it, then the manner of its family. A character with no hands plays the
 * same look; the arm channels move nothing on it. The hand travels to the
 * joints' own envelope (`LIMB_LIMITS`: 18° for the arm, 14° for the wrist)
 * and no further: asked for more, the clamp stopped it dead mid-gesture. */
export function presentationTapes(gesture: PresentationGesture): Tape[] {
  return [
    relative(
      'gazeY',
      [
        [0, 0],
        [150, 0.62],
        [640, 0.6],
        [860, 0],
      ],
      1150,
      ACCENT
    ),
    relative(
      'massY',
      [
        [80, 0.03],
        [640, 0.03],
        [860, 0],
      ],
      1150,
      SOFT
    ),
    relative(
      'massX',
      [
        [80, 0.02],
        [640, 0.02],
        [860, 0],
      ],
      1150,
      SOFT
    ),
    relative(
      'armR',
      [
        [0, 0],
        [170, 3],
        [460, -18],
        [1300, -16],
        [1750, 0],
      ],
      2100,
      HAND
    ),
    relative(
      'wristR',
      [
        [260, 0],
        [540, -14],
        [1300, -12],
        [1750, 0],
      ],
      2100,
      HAND
    ),
    ...MANNERS[gesture](MANNER_AT_MS),
  ];
}

/** The tapes of a delivery gesture, or null for any other gesture: the one
 * door `gestureTapes` asks before its own vocabulary. */
export function deliveryTapes(gesture: IdleGesture): Tape[] | null {
  if (gesture === 'listen') return listenTapes();
  return isPresentationGesture(gesture) ? presentationTapes(gesture) : null;
}

/** « À toi »: the face leans in a little and waits, alive, then lets go. */
export function listenTapes(): Tape[] {
  const held = (value: number, release: number): Keys => [
    [300, value],
    [2800, release],
    [3500, 0],
  ];
  return [
    relative(
      'mass',
      [
        [0, 0],
        [650, 0.035],
        [2800, 0.035],
        [3500, 0],
      ],
      3900,
      SETTLE
    ),
    relative('tilt', held(3, 3), 3900, SETTLE),
    ...bothSides('browY', held(-0.03, -0.022), 3900, SETTLE),
    ...bothSides('browArc', held(0.16, 0.12), 3900, SETTLE),
    relative(
      'mouthCurve',
      [
        [400, 0.05],
        [2800, 0.04],
        [3500, 0],
      ],
      3900,
      SETTLE
    ),
    ...blink(1600, 120),
  ];
}
