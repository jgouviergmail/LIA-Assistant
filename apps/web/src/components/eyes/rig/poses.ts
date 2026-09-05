/**
 * Pose tables — the expression recipes and the style sheets, as DATA.
 *
 * This module is the migration of two stylesheet sections ("Expression
 * recipes" and "STYLE SHEETS") into the rig, following the boundary rule: a
 * radius, a slant or a lid depth MOVES, so it belongs here; a width, a border
 * or a fill is DRAWN, so it stays in `styles/eyes.css`.
 *
 * Resolution order, and it is load-bearing:
 *
 *   rest  <  style geometry  <  expression recipe  <  style × expression
 *
 * A style's neutral silhouette is laid down FIRST so a generic recipe can
 * reshape it, and the style keeps the last word on its own expressions. The
 * inverse order is precisely the bug that shipped in 2026-08: generic radii
 * out-inheriting each style's silhouette turned all six styles into Cozmo.
 */

import {
  CHANNELS,
  restChannelValues,
  type ChannelValues,
  type EyeChannelBase,
  type PartialChannelValues,
} from '@/components/eyes/rig/channels';
import type { LoopSpec } from '@/components/eyes/rig/loops';
import type { EyeExpression, IdleMoodFamily } from '@/components/eyes/expression-engine';
import type { EyeStyleId } from '@/components/eyes/eye-styles';

// =============================================================================
// Declaration helpers — a pose reads as a sentence, not as a key list
// =============================================================================

/** Same value on both eyes. */
function both(base: EyeChannelBase, value: number): PartialChannelValues {
  return { [`${base}L`]: value, [`${base}R`]: value } as PartialChannelValues;
}

/** Mirrored (or plainly different) values — asymmetry made explicit. */
function pair(base: EyeChannelBase, left: number, right: number): PartialChannelValues {
  return { [`${base}L`]: left, [`${base}R`]: right } as PartialChannelValues;
}

function merge(...parts: readonly PartialChannelValues[]): PartialChannelValues {
  return Object.assign({}, ...parts) as PartialChannelValues;
}

/** The four silhouette radii of one style, in em. */
function radii(top: number, vTop: number, bottom: number, vBottom: number): PartialChannelValues {
  return merge(
    both('rTop', top),
    both('rvTop', vTop),
    both('rBot', bottom),
    both('rvBot', vBottom)
  );
}

/** Radii on the LEFT eye only — the wink keeps the right eye shut and the
 * left one smiling, so it re-uses joy's silhouette on that side alone. */
function leftRadii(
  top: number,
  vTop: number,
  bottom: number,
  vBottom: number
): PartialChannelValues {
  return { rTopL: top, rvTopL: vTop, rBotL: bottom, rvBotL: vBottom };
}

/**
 * The brow, in one line: how PRESENT it is, how high it sits (negative is
 * raised), the tilt of each eye's INNER end, and how much it ARCHES.
 *
 * The tilt is half the grammar, and it is mirrored: a positive angle on the
 * left eye and a negative one on the right both lower the inner ends, which
 * is a scowl; the opposite pair raises them, which is grief, worry or
 * tenderness depending on what the rest of the face is doing. The arch is
 * the other half: a scowl is a flat bar pressed down, a startle is a full
 * arch flung up, and tenderness is a gentle curve — a bar that can only
 * tilt plays half of that. Three numbers carry more emotion than the entire
 * silhouette does.
 */
function brow(
  presence: number,
  y: number,
  rotL: number,
  rotR: number,
  arcL: number,
  arcR = arcL
): PartialChannelValues {
  return merge(
    both('browA', presence),
    both('browY', y),
    pair('browRot', rotL, rotR),
    pair('browArc', arcL, arcR)
  );
}

/** Pupil dilation. Fear pinpoints, tenderness blows wide open — the one
 * signal a viewer reads without knowing they are reading it. */
function pupils(scale: number): PartialChannelValues {
  return both('pupil', scale);
}

/**
 * The mouth: how PRESENT it is, its CURVE, its width, and how far it parts.
 *
 * The curve is signed and that is the whole grammar — positive lifts the
 * corners, negative drops them, zero is the flat line the two pass through.
 * Unlike the brow, the mouth is never absent: a face that grows a mouth when
 * it smiles is a face with a defect. It is quiet at rest instead (a short,
 * barely curved line) and it commits when the emotion does.
 */
function mouth(
  presence: number,
  curve: number,
  width = 1,
  open = 0,
  skew = 0
): PartialChannelValues {
  return {
    mouthA: presence,
    mouthCurve: curve,
    mouthW: width,
    mouthOpen: open,
    mouthSkew: skew,
  };
}

/** A stroke style draws its expressions instead of squashing them: the pose
 * has to stand down so the CSS silhouette can speak. */
const UNSQUASHED = merge(both('sy', 1), both('oy', 50), both('ty', 0));

/** No sustained lid at all — for the states a style DRAWS closed. */
const NO_LIDS = merge(both('lidTop', 0), both('lidBot', 0), both('lidR', 0));

// =============================================================================
// Expression recipes — style-agnostic motion
// =============================================================================

const JOY_DOME = merge(both('sy', 0.55), both('oy', 20), both('ty', -0.08));

export const POSES: Record<EyeExpression, PartialChannelValues> = {
  neutral: {},

  /** Screens widen and lift — "I'm all ears". */
  attentive: merge(
    both('sy', 1.12),
    both('sx', 1.04),
    both('ty', -0.03),
    brow(0.7, -0.05, -2, 2, 0.3),
    pupils(1.05),
    mouth(0.7, 0.15, 0.95, 0, 0.11)
  ),

  /** A rising dome — round crown, flat base. The eye smiles. */
  joy: merge(JOY_DOME, brow(0.6, -0.05, -4, 4, 0.5), pupils(1.15), mouth(1, 0.9, 1.15, 0.12, 0.18)),

  /** A livelier dome, plus the bounce loop below. */
  excited: merge(
    both('sy', 0.7),
    both('oy', 25),
    both('sx', 1.05),
    brow(0.9, -0.09, -6, 6, 0.6),
    pupils(1.2),
    mouth(1, 1, 1.2, 0.35, 0.14)
  ),

  /** Soft heavy lids and a gentle inward lean — the melted look. */
  tender: merge(
    both('sy', 0.94),
    both('oy', 30),
    both('ty', -0.02),
    both('lidTop', 26),
    both('lidR', 0.55),
    pair('rot', 3, -3),
    // Inner ends UP: the compassionate brow. Without it, heavy lids alone
    // read as sleepiness rather than tenderness.
    brow(0.65, -0.02, -8, 8, 0.45),
    pupils(1.3),
    mouth(0.9, 0.5, 0.9, 0, 0.17)
  ),

  /** Big rounded screens — the pop is an arrival tape, not a pose. */
  surprise: merge(
    both('sx', 1.12),
    both('sy', 1.25),
    brow(1, -0.14, 0, 0, 0.85),
    pupils(1.35),
    mouth(1, 0, 0.7, 0.75)
  ),

  /** Shrunken screens, trembling (loop below). */
  // Pinpoint pupils under raised inner brows: the two cues that separate
  // fear from surprise, which share almost everything else.
  fear: merge(
    both('sx', 0.85),
    both('sy', 0.85),
    brow(1, -0.1, -16, 16, 0.55),
    pupils(0.55),
    mouth(1, -0.5, 0.85, 0.3, -0.1)
  ),

  /** Screens press down and tip toward the nose — the slant IS the brow. */
  anger: merge(
    both('sy', 0.95),
    both('oy', 100),
    both('ty', 0.03),
    both('lidTop', 34),
    both('lidR', 0.28),
    pair('rot', 7, -7),
    brow(1, 0.02, 18, -18, 0),
    pupils(0.7),
    mouth(1, -0.7, 0.85, 0.1, 0.18)
  ),

  /** The mirror lean — outer corners sink, the gaze rides low. */
  sad: merge(
    both('sy', 0.68),
    both('oy', 100),
    both('ty', 0.05),
    pair('rot', -6, 6),
    brow(1, -0.02, -16, 16, 0.35),
    pupils(1.1),
    mouth(1, -0.85, 0.85, 0, -0.06)
  ),

  /** A softer, slighter sadness. */
  worried: merge(
    both('sy', 0.85),
    both('oy', 90),
    pair('rot', -3, 3),
    brow(0.85, -0.03, -10, 10, 0.4),
    pupils(1.05),
    mouth(0.9, -0.45, 0.9, 0, 0.13)
  ),

  /** One raised screen — the asymmetry is the whole message. */
  question: merge(
    { syL: 1.12, tyL: -0.04 },
    { syR: 0.66, oyR: 100, rotR: -5 },
    // One brow up, the other settled: the single most legible "oh?" a face
    // can make, and it needs no eye at all.
    { browAL: 0.9, browAR: 0.9, browYL: -0.12, browYR: 0.01, browRotL: -8, browRotR: -6 },
    { browArcL: 0.7, browArcR: 0.1 },
    pupils(1.05),
    mouth(0.8, 0.1, 0.75, 0, 0.3)
  ),

  /** Half-lidded from above; the engine aims the gaze up. */
  thinking: merge(
    both('sy', 0.6),
    both('oy', 60),
    { browAL: 0.7, browAR: 0.7, browYL: -0.08, browYR: 0, browRotL: -5, browRotR: 8 },
    { browArcL: 0.5, browArcR: 0.05 },
    pupils(0.9),
    mouth(0.7, -0.15, 0.7, 0, 0.35)
  ),

  /** A light squint. The looking itself is a SACCADE pattern (see
   * `rig/scripts.ts`): a smooth sweep is a security camera, not a search. */
  searching: merge(
    both('sy', 0.7),
    both('oy', 55),
    brow(0.6, -0.04, 0, 0, 0.25),
    pupils(0.95),
    mouth(0.6, 0, 0.8, 0, 0.1)
  ),

  /** Concentrated slits — squeezed from BOTH lids. */
  focused: merge(
    both('sx', 1.05),
    both('lidTop', 30),
    both('lidBot', 24),
    both('lidR', 0.45),
    brow(1, 0.03, 10, -10, 0),
    pupils(0.72),
    mouth(0.9, -0.2, 0.7, 0, 0.09)
  ),

  /** Speaking finally SPEAKS: the flap below is the life, and the eyes only
   * carry the bob that goes with it. */
  speaking: merge(brow(0.55, -0.04, -2, 2, 0.25), mouth(1, 0.2, 1, 0.18)),

  /** Heavy flat lids from above — the stillness is the point. */
  bored: merge(
    both('oy', 100),
    both('lidTop', 46),
    both('lidR', 0.4),
    brow(0.5, 0.02, 4, -4, 0),
    pupils(0.95),
    mouth(0.7, -0.25, 0.8, 0, 0.28)
  ),

  /** Heavy lids and a light outward droop. */
  tired: merge(
    both('sy', 0.97),
    both('oy', 100),
    both('lidTop', 38),
    both('lidR', 0.5),
    pair('rot', -2, 2),
    brow(0.5, 0.01, -6, 6, 0.2),
    mouth(0.6, -0.3, 0.85, 0, -0.08)
  ),

  /** Almost closed; everything slows down. */
  sleepy: merge(
    both('oy', 100),
    both('lidTop', 58),
    both('lidBot', 5),
    both('lidR', 0.5),
    brow(0.3, 0.02, -4, 4, 0.1),
    mouth(0.5, -0.15, 0.7, 0, 0.12)
  ),

  /** A soft closed lens, deep slow breathing. The brows relax rather than
   * vanish: a sleeper still has a face. */
  sleep: merge(
    both('oy', 85),
    both('lidTop', 82),
    both('lidBot', 4),
    both('lidR', 0.6),
    brow(0.3, 0.03, -2, 2, 0.06),
    mouth(0.4, 0.15, 0.6, 0.14, 0.05)
  ),

  /** The right eye shuts outright; the left keeps joy's dome. */
  wink: merge(
    JOY_DOME,
    { blinkR: 1 },
    { browAL: 0.7, browAR: 0.8, browYL: -0.06, browYR: -0.02, browRotL: -6, browRotR: 4 },
    { browArcL: 0.5, browArcR: 0.15 },
    pupils(1.1),
    mouth(1, 0.7, 1.05, 0, 0.32)
  ),
};

// =============================================================================
// Style geometry — each style's NEUTRAL silhouette (what the sheets declared
// as base radii and base tilt). Cozmo is the rest pose, so it declares none.
// =============================================================================

export const STYLE_GEOMETRY: Record<EyeStyleId, PartialChannelValues> = {
  cozmo: {},
  capsules: radii(0.5, 0.5, 0.5, 0.5),
  billes: radii(0.58, 0.58, 0.58, 0.58),
  amande: merge(radii(0.55, 0.42, 0.55, 0.42), pair('baseRot', -12, 12)),
  traits: radii(0.21, 0.21, 0.21, 0.21),
  anneaux: radii(0.53, 0.53, 0.53, 0.53),
};

// =============================================================================
// Style × expression — the last word, for the styles that re-shape a pose
// =============================================================================

type StyleOverrides = Partial<Record<EyeExpression, PartialChannelValues>>;

export const STYLE_POSE_OVERRIDES: Partial<Record<EyeStyleId, StyleOverrides>> = {
  /** Cozmo's screens re-shape their corners per emotion — a dome for joy,
   * a hard corner for the scowl, a lens for focus. */
  cozmo: {
    joy: radii(0.42, 0.46, 0.12, 0.1),
    wink: leftRadii(0.42, 0.46, 0.12, 0.1),
    excited: radii(0.4, 0.42, 0.18, 0.14),
    tender: radii(0.4, 0.42, 0.2, 0.16),
    surprise: radii(0.34, 0.34, 0.34, 0.34),
    fear: radii(0.3, 0.34, 0.3, 0.34),
    anger: merge(both('rTop', 0.1), both('rvTop', 0.08)),
    focused: radii(0.16, 0.14, 0.16, 0.14),
    bored: merge(both('rTop', 0.16), both('rvTop', 0.12)),
  },
  capsules: {
    joy: radii(0.55, 0.62, 0.34, 0.18),
    wink: leftRadii(0.55, 0.62, 0.34, 0.18),
    anger: merge(both('rTop', 0.34), both('rvTop', 0.26)),
    focused: radii(0.42, 0.3, 0.42, 0.3),
    bored: merge(both('rTop', 0.42), both('rvTop', 0.34)),
  },
  billes: {
    joy: radii(0.6, 0.62, 0.34, 0.12),
    wink: leftRadii(0.6, 0.62, 0.34, 0.12),
    anger: merge(both('rTop', 0.42), both('rvTop', 0.3)),
  },
  /** The almond leans by nature: it scowls harder, grieves deeper, and
   * straightens up when startled or asleep. */
  amande: {
    anger: pair('rot', 12, -12),
    sad: pair('rot', -14, 14),
    surprise: both('baseRot', 0),
    sleep: both('baseRot', 0),
  },
  /** Strokes are DRAWN by the stylesheet (arch, bar, ring): the pose must not
   * squash them, or the drawing gets crushed on top of its own shape. */
  traits: {
    joy: UNSQUASHED,
    wink: merge(UNSQUASHED, { blinkR: 1 }),
    sad: merge(UNSQUASHED, both('ty', 0.08), both('rot', 0)),
    anger: merge(both('sy', 1), both('oy', 50), pair('rot', 24, -24)),
    // The stroke states its own closure: the sheet already collapses the bar
    // to a dash for these two, so the lids must stand down or the squash they
    // fold into compounds with it and the eye disappears (measured in a
    // browser: 1.2 px at the medium size).
    sleepy: merge(both('sy', 1), both('oy', 50), NO_LIDS),
    sleep: merge(both('sy', 1), both('oy', 50), NO_LIDS),
  },
  /** Rings keep their circle: joy is an arch drawn by the border, not a
   * flattened disc. */
  anneaux: {
    joy: merge(UNSQUASHED, both('ty', -0.06)),
    wink: merge(UNSQUASHED, both('ty', -0.06), { blinkR: 1 }),
  },
};

/**
 * How a style CLOSES an eye.
 *
 * `clip` covers an intact eye with a curved lid — the right answer for
 * anything with a surface, because a scaled squint crushes the artwork
 * (catch-lights included) like a squeezed photograph.
 *
 * `squash` flattens the whole shape instead, and it is the only workable
 * answer for the two drawn languages: a clipped RING comes back as two
 * disconnected side arcs, and a clipped STROKE narrower than the lid radius
 * comes back as a dot. Both were verified in a browser (2026-08-31): with
 * `focused`, `traits` rendered two specks and `anneaux` rendered "( • )".
 * The blink already had this exception; the SUSTAINED lids never did.
 */
export const STYLE_LID_MODE: Record<EyeStyleId, 'clip' | 'squash'> = {
  cozmo: 'clip',
  capsules: 'clip',
  billes: 'clip',
  amande: 'clip',
  traits: 'squash',
  anneaux: 'squash',
};

/**
 * Rewrite a pose's sustained lids as an equivalent vertical squash.
 *
 * The band a lid would have LEFT VISIBLE becomes the height the shape is
 * scaled to, anchored on that band's own centre, so the eye ends up exactly
 * where the clip would have shown it — flattened rather than cropped.
 * Derived from the lid values instead of hand-written per expression: a
 * dozen transcriptions would drift the first time a recipe is retuned.
 */
function foldLidsIntoSquash(pose: ChannelValues): ChannelValues {
  const folded: ChannelValues = { ...pose };
  for (const side of ['L', 'R'] as const) {
    const top = folded[`lidTop${side}`];
    const bottom = folded[`lidBot${side}`];
    const covered = top + bottom;
    if (covered <= 0) continue;
    const visible = Math.max(0, 100 - covered);
    folded[`sy${side}`] = folded[`sy${side}`] * (visible / 100);
    folded[`oy${side}`] = top + visible / 2;
    folded[`lidTop${side}`] = 0;
    folded[`lidBot${side}`] = 0;
    folded[`lidR${side}`] = 0;
  }
  return folded;
}

/** The complete channel set an expression resolves to, for one style. */
export function resolvePose(expression: EyeExpression, styleId: EyeStyleId): ChannelValues {
  const pose: ChannelValues = {
    ...restChannelValues(),
    ...STYLE_GEOMETRY[styleId],
    ...POSES[expression],
    ...(STYLE_POSE_OVERRIDES[styleId]?.[expression] ?? {}),
  };
  return STYLE_LID_MODE[styleId] === 'squash' ? foldLidsIntoSquash(pose) : pose;
}

/**
 * Exaggeration scales what the face WILLS — its pose and its mass — and
 * nothing else. The same split as anticipation, for the same reason.
 *
 * The groups it leaves alone each state a FACT rather than an intensity: a
 * lid says how open the eye is (a drowsy `sleep` scaled to 92 % would be a
 * character sleeping with its eyes ajar — caught by a test, not by reading),
 * a radius is the style's silhouette, a blink either closes or it does not,
 * and the stretch is derived from motion that has already been scaled.
 */
const EXAGGERATED_GROUPS: ReadonlySet<string> = new Set(['pose', 'mass']);

/**
 * Scale an expression's DEVIATION from its style's neutral.
 *
 * Measuring the deviation from the style neutral rather than from the channel
 * rest value is what keeps exaggeration from eating the style's identity: a
 * drowsy `billes` must still be a circle, and scaling its radius toward the
 * default silhouette would quietly turn it into something else.
 */
export function exaggeratePose(
  neutral: ChannelValues,
  pose: ChannelValues,
  amplitude: number
): ChannelValues {
  if (amplitude === 1) return pose;
  const scaled: Record<string, number> = {};
  for (const key of Object.keys(pose) as (keyof ChannelValues)[]) {
    const base = neutral[key];
    scaled[key] = EXAGGERATED_GROUPS.has(CHANNELS[key].group)
      ? base + (pose[key] - base) * amplitude
      : pose[key];
  }
  return scaled as ChannelValues;
}

// =============================================================================
// Loops — the motion that never arrives anywhere
// =============================================================================

/** Breathing pace and depth per mood family: a lively character breathes
 * quicker and fuller, a drowsy one slower and shallower. Amplitudes are half
 * the peak-to-peak travel the keyframes declared. */
const BREATH_BY_FAMILY: Record<IdleMoodFamily, { periodMs: number; scale: number }> = {
  lively: { periodMs: 3600, scale: 0.0175 },
  calm: { periodMs: 4600, scale: 0.0125 },
  drowsy: { periodMs: 6200, scale: 0.0075 },
};

/** Expressions calm enough to breathe (the stylesheet's own list). */
const BREATHING: ReadonlySet<EyeExpression> = new Set([
  'neutral',
  'attentive',
  'tender',
  'joy',
  'bored',
  'tired',
  'thinking',
]);

/** Drowsiness breathes on its own clock, whatever the mood says. */
const SLEEPY_BREATH_MS = 6000;

/**
 * A breath, and the reason it is not one sine.
 *
 * A single sine repeats exactly, and a repetition long enough to notice is
 * heard as a machine. Adding a second component at an incommensurable period
 * (the golden ratio — the least rational number there is) means the sum never
 * comes back to the same shape, for the cost of two multiplications. Real
 * breathing is not periodic either.
 */
const BREATH_SECOND_RATIO = 1.618;
const BREATH_SECOND_WEIGHT = 0.34;

/** The right eye also moves slightly FURTHER, not just later: two eyes doing
 * the same thing at the same size, however offset in time, still read as a
 * mechanism. */
const RIGHT_AMPLITUDE_JITTER = 1.06;

/**
 * How far the breath reaches the brows and the mouth, per unit of mass scale.
 *
 * ONE breath goes through the whole face, or it is three organs twitching on
 * three timers: on the inhale the mass grows, the brows lift a hair (negative
 * is up) and the mouth widens a touch, each on the SAME period as the mass and
 * a beat behind it — what follows the breath waits for it. Sized from the
 * family's own depth, so a drowsy face breathes shallower everywhere at once.
 * Calibrated on screen and held by the pixel-budget test: at the calm depth
 * the brows travel 0.8 px peak-to-peak at the medium size and 1.2 px at the
 * large one, the mouth width 1.3 px — and the liveliest family at the largest
 * size stays under the two-pixel fidget line, right brow jitter included.
 * (First shipped at 0.4 px, which the owner read as static next to the eyes.)
 */
const BREATH_BROW_EM_PER_SCALE = -1.1;
const BREATH_MOUTH_WIDTH_PER_SCALE = 1.9;
/** The brows follow the mass by a fraction of a turn, the mouth a little more. */
const BREATH_BROW_LAG = 0.985;
const BREATH_MOUTH_LAG = 0.97;

function breathLoops(periodMs: number, scale: number): LoopSpec[] {
  const second = periodMs * BREATH_SECOND_RATIO;
  const brow = scale * BREATH_BROW_EM_PER_SCALE;
  return [
    { channel: 'mass', amplitude: scale, periodMs, phase: 0, waveform: 'sine' },
    {
      channel: 'mass',
      amplitude: scale * BREATH_SECOND_WEIGHT,
      periodMs: second,
      phase: 0.23,
      waveform: 'sine',
    },
    { channel: 'massY', amplitude: -0.015, periodMs, phase: 0, waveform: 'sine' },
    {
      channel: 'massY',
      amplitude: -0.015 * BREATH_SECOND_WEIGHT,
      periodMs: second * 0.83,
      phase: 0.61,
      waveform: 'sine',
    },
    // The face breathes with the mass: a phase just under a full turn is a
    // short delay behind it (the sine is periodic), and the right brow trails
    // the left as everything on the right does.
    { channel: 'browYL', amplitude: brow, periodMs, phase: BREATH_BROW_LAG, waveform: 'sine' },
    {
      channel: 'browYR',
      amplitude: brow * RIGHT_AMPLITUDE_JITTER,
      periodMs,
      phase: BREATH_BROW_LAG - 0.008,
      waveform: 'sine',
    },
    {
      channel: 'mouthW',
      amplitude: scale * BREATH_MOUTH_WIDTH_PER_SCALE,
      periodMs,
      phase: BREATH_MOUTH_LAG,
      waveform: 'sine',
    },
  ];
}

/** One loop per eye, the right one deliberately out of step. */
function eyeLoop(
  base: EyeChannelBase,
  amplitude: number,
  periodMs: number,
  phase: number,
  options: { rightPeriodMs?: number; rightDelayMs?: number; waveform?: LoopSpec['waveform'] } = {}
): LoopSpec[] {
  const rightPeriod = options.rightPeriodMs ?? periodMs;
  const waveform = options.waveform ?? 'sine';
  const rightPhase = (phase + (options.rightDelayMs ?? 0) / rightPeriod) % 1;
  return [
    { channel: `${base}L`, amplitude, periodMs, phase, waveform },
    {
      channel: `${base}R`,
      amplitude: amplitude * RIGHT_AMPLITUDE_JITTER,
      periodMs: rightPeriod,
      phase: rightPhase,
      waveform,
    },
  ];
}

/**
 * The moving hold — the reason a resting face still reads as alive.
 *
 * A settled pose is a frozen pose, and a frozen face is the single strongest
 * cue that there is nobody behind it. Real eyes never stop: ocular drift and
 * microsaccades keep them wandering by a fraction of a degree. Two sines with
 * incommensurable periods per axis are enough — their sum never repeats on
 * any timescale a viewer can catch, and it costs two multiplications.
 *
 * It rides the existing loop mechanism on purpose: no new machinery, no new
 * "always awake" surface, and it is paced by the mood family like everything
 * else that idles.
 */
const DRIFT_LOOPS: readonly LoopSpec[] = [
  { channel: 'gazeX', amplitude: 0.022, periodMs: 5300, phase: 0, waveform: 'sine' },
  { channel: 'gazeX', amplitude: 0.014, periodMs: 8700, phase: 0.37, waveform: 'sine' },
  { channel: 'gazeY', amplitude: 0.018, periodMs: 6100, phase: 0.61, waveform: 'sine' },
  { channel: 'gazeY', amplitude: 0.011, periodMs: 9700, phase: 0.13, waveform: 'sine' },
  { channel: 'rotL', amplitude: 0.12, periodMs: 7300, phase: 0.2, waveform: 'sine' },
  { channel: 'rotR', amplitude: 0.14, periodMs: 8100, phase: 0.66, waveform: 'sine' },
  // A resting MOUTH is never quite still either — the corners wander on
  // their own long clocks (its width breathes with the mass, above). Sized
  // to cross the pixel: 0.03 of curve was 0.23 px at the medium size, which
  // is a still image with a number attached.
  { channel: 'mouthCurve', amplitude: 0.06, periodMs: 7900, phase: 0.44, waveform: 'sine' },
  { channel: 'mouthSkew', amplitude: 0.09, periodMs: 11300, phase: 0.18, waveform: 'sine' },
];

/**
 * Chewing on a thought. A held `thinking` is the one resting pose where the
 * mouth WORKS: the corners shift and the width pulls, quicker than the drift
 * and slower than speech, on two clocks that never line up.
 */
const CHEW_LOOPS: readonly LoopSpec[] = [
  { channel: 'mouthSkew', amplitude: 0.07, periodMs: 2300, phase: 0.3, waveform: 'sine' },
  { channel: 'mouthW', amplitude: 0.025, periodMs: 3100, phase: 0.7, waveform: 'sine' },
];

/** The sleeper's breath period — the eyes' own slow swell. */
const SLEEP_BREATH_MS = 4200;

/**
 * The loops an expression runs, paced by the mood family.
 *
 * Phase conventions: a negative amplitude on `ty` lifts (screen coordinates),
 * and the bounce lifts BEFORE it stretches — an eye that stretches on the way
 * down is an eye falling, which is a different beat entirely.
 */
export function resolveLoops(expression: EyeExpression, family: IdleMoodFamily): LoopSpec[] {
  switch (expression) {
    case 'excited':
      return [
        ...eyeLoop('ty', 0.055, 760, 0.5, { rightDelayMs: 90 }),
        ...eyeLoop('sy', 0.03, 760, 0, { rightDelayMs: 90 }),
      ];
    case 'speaking':
      return [
        ...eyeLoop('ty', 0.014, 900, 0.5, { rightPeriodMs: 980, rightDelayMs: 120 }),
        ...eyeLoop('sy', 0.015, 900, 0, { rightPeriodMs: 980, rightDelayMs: 120 }),
        // The flap. ~260 ms is roughly a syllable; the second, longer
        // component keeps it from ticking like a metronome, which is exactly
        // what a single sine on a mouth looks like once you watch it.
        { channel: 'mouthOpen', amplitude: 0.13, periodMs: 260, phase: 0, waveform: 'sine' },
        { channel: 'mouthOpen', amplitude: 0.05, periodMs: 430, phase: 0.31, waveform: 'sine' },
        // The PHRASES. Speech stops: a slow envelope, held at its ends, drives
        // the flap through the closure (the rig bounds the opening at zero)
        // for a few hundred milliseconds between two runs of talk, and a
        // second, slower sine keeps those pauses from landing on a beat.
        // Three sines alone only ever got quieter and louder.
        { channel: 'mouthOpen', amplitude: -0.11, periodMs: 3700, phase: 0.55, waveform: 'hold' },
        { channel: 'mouthOpen', amplitude: -0.04, periodMs: 5300, phase: 0.2, waveform: 'sine' },
        // Speech widens and narrows a mouth as much as it opens it...
        { channel: 'mouthW', amplitude: 0.06, periodMs: 370, phase: 0.5, waveform: 'sine' },
        // ...and it changes its SHAPE, which is what separates talking from
        // chewing: a mouth that only opens and shuts on one axis reads as a
        // hinge. These two put a different form on each syllable.
        { channel: 'mouthCurve', amplitude: 0.12, periodMs: 610, phase: 0.2, waveform: 'sine' },
        { channel: 'mouthSkew', amplitude: 0.1, periodMs: 830, phase: 0.6, waveform: 'sine' },
      ];
    case 'fear':
      return [
        { channel: 'massX', amplitude: 0.016, periodMs: 130, phase: 0, waveform: 'triangle' },
      ];
    case 'sleepy':
      return breathLoops(SLEEPY_BREATH_MS, BREATH_BY_FAMILY.drowsy.scale);
    case 'sleep':
      return [
        ...eyeLoop('sy', 0.02, SLEEP_BREATH_MS, 0, { rightDelayMs: 180 }),
        ...eyeLoop('sx', 0.015, SLEEP_BREATH_MS, 0.5, { rightDelayMs: 140 }),
        // A sleeper breathes through a mouth that hangs a little open — on
        // the same slow clock as the eyes' swell, not on a syllable.
        {
          channel: 'mouthOpen',
          amplitude: 0.04,
          periodMs: SLEEP_BREATH_MS,
          phase: 0.1,
          waveform: 'sine',
        },
      ];
    case 'thinking': {
      const breath = BREATH_BY_FAMILY[family];
      return [...breathLoops(breath.periodMs, breath.scale), ...DRIFT_LOOPS, ...CHEW_LOOPS];
    }
    default: {
      if (!BREATHING.has(expression)) return [];
      const breath = BREATH_BY_FAMILY[family];
      return [...breathLoops(breath.periodMs, breath.scale), ...DRIFT_LOOPS];
    }
  }
}
