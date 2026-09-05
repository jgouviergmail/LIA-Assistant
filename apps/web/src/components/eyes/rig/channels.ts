/**
 * Channel table — the rig's vocabulary.
 *
 * A channel is ONE animated scalar. Everything the eyes do at runtime is a
 * combination of these numbers, and every one of them surfaces as a
 * `--rig-*` custom property the stylesheet consumes. That prefix is the
 * enforceable half of the system's boundary rule:
 *
 *   TS owns what MOVES (these channels). CSS owns what is DRAWN (silhouette,
 *   skin, matter). A stylesheet READS `--rig-*`; it never DECLARES one.
 *
 * Per-eye channels are declared once and mirrored into an `L`/`R` pair, so an
 * asymmetry is always a pose decision and never a table typo. Rest values are
 * the neutral pose of the DEFAULT style (`cozmo`); every other style restates
 * its own neutral through the style geometry table, never through CSS.
 */

/**
 * A note on PRECISION, which is not cosmetic here.
 *
 * It is the write threshold of the render loop: a value whose change cannot
 * alter its own text is never formatted and never reaches the DOM. Four
 * decimals on a gaze unit is 0.006 px of travel — invisible, and paid for on
 * every frame of every idle minute, because the perpetual drift crosses that
 * step constantly. Three decimals is still under a tenth of a pixel and halves
 * the idle writes.
 */

/** How a channel serializes into CSS. */
export type ChannelUnit = 'num' | 'em' | 'deg' | 'pct';

/**
 * Dynamics group. A dynamics preset tunes GROUPS, not the 40-odd channels
 * one by one: an emotion says "lids are heavy and the mass is slow", never
 * forty stiffness numbers.
 */
export type ChannelGroup =
  | 'gaze'
  | 'pose'
  | 'lid'
  | 'blink'
  | 'mass'
  | 'radius'
  | 'aura'
  | 'organ'
  | 'mouth'
  | 'stretch';

export interface ChannelDef {
  /** Custom property the runtime writes (always `--rig-*`). */
  readonly cssVar: string;
  /** Neutral value — the pose fallback and the SSR/no-JS rendering. */
  readonly rest: number;
  readonly unit: ChannelUnit;
  readonly group: ChannelGroup;
  /** Decimals kept when serializing. This IS the change threshold of the
   * write loop: a move too small to alter the string is not written. */
  readonly precision: number;
  /** Step channels: no physics, the target lands at once. `transform-origin`
   * is the canonical case — interpolating an origin makes the scaled shape
   * SLIDE sideways, which reads as positional drift (proven regression). */
  readonly snap: boolean;
  /** Derived channels are COMPUTED from the rig's own motion (the velocity
   * squash and its axis), never sprung and never targeted by a pose. They are
   * published like any other channel because the stylesheet consumes them the
   * same way. */
  readonly derived?: boolean;
  /** Internal channels are sprung like any other but are NOT drawn: the rig
   * reads them to compute something else. `mouthCurve` is the case — the
   * stylesheet consumes the arc and the flip derived FROM it, never the signed
   * curve itself. The boundary guard still holds them to account: an internal
   * channel nothing reads is as dead as an unconsumed one. */
  readonly internal?: boolean;
}

type ChannelSpec = Omit<ChannelDef, 'cssVar'> & { readonly cssVar?: never };

/** Channels the spring loop must skip: they are computed, not integrated. */
export function isDerived(key: ChannelKey): boolean {
  return CHANNELS[key].derived === true;
}

const GLOBAL_SPECS = {
  /** Normalized gaze, [-1, 1]. The stylesheet turns it into em travel. */
  gazeX: { rest: 0, unit: 'num', group: 'gaze', precision: 3, snap: false },
  gazeY: { rest: 0, unit: 'num', group: 'gaze', precision: 3, snap: false },
  /** Head tilt of the whole pair. */
  tilt: { rest: 0, unit: 'deg', group: 'mass', precision: 2, snap: false },
  /** Breathing / pop / perk scale of the whole pair. */
  mass: { rest: 1, unit: 'num', group: 'mass', precision: 3, snap: false },
  /** Vertical travel of the whole pair (breath lift, bounce). */
  massY: { rest: 0, unit: 'em', group: 'mass', precision: 3, snap: false },
  /** Horizontal travel of the whole pair (the fear shiver). */
  massX: { rest: 0, unit: 'em', group: 'mass', precision: 3, snap: false },
  /** Halo intensity multiplier — emotion reaches the light, not just the form. */
  glow: { rest: 1, unit: 'num', group: 'aura', precision: 3, snap: false },
  /** Where the CATCH-LIGHTS think the light is.
   *
   * They chase the gaze on the slow `aura` spring, so they arrive after the
   * eye does and drift past it on the way back. A highlight rigidly welded
   * to the eye reads as a painted dot; one that lags by a fraction of a
   * second reads as a reflection on something wet. */
  hlX: { rest: 0, unit: 'num', group: 'aura', precision: 3, snap: false },
  hlY: { rest: 0, unit: 'num', group: 'aura', precision: 3, snap: false },
  /**
   * The MOUTH — singular, so global rather than per-eye.
   *
   * `mouthCurve` is SIGNED and it is the whole grammar: a smile and a frown
   * are not two shapes, they are one shape and a sign. Positive lifts the
   * corners, negative drops them, and zero is a flat line the two pass
   * through continuously — which is only true because the curve is one
   * channel instead of a pair the poses would have to keep consistent.
   */
  mouthA: { rest: 0.5, unit: 'num', group: 'aura', precision: 3, snap: false },
  mouthCurve: {
    // A resting face is faintly pleasant, not flat: a dead straight line under
    // two eyes reads as stern, which is not what this character is.
    rest: 0.12,
    unit: 'num',
    group: 'pose',
    precision: 4,
    snap: false,
    internal: true,
  },
  /** A resting mouth is SMALL. Expression widens it; leaving it at full span
   * makes a calm face read as a long dash under two eyes. */
  mouthW: { rest: 0.72, unit: 'num', group: 'pose', precision: 3, snap: false },
  /**
   * The CORNERS, as one signed number: positive lifts the left corner and
   * drops the right, negative the reverse.
   *
   * This is where cartoon acting actually lives. A mouth that can only be
   * symmetric can play happy and unhappy and nothing else; one corner out
   * of step with the other is a smirk, a doubt, a sneer, a thought being
   * chewed — the whole register between the two extremes.
   */
  mouthSkew: { rest: 0, unit: 'num', group: 'pose', precision: 3, snap: false },
  mouthY: { rest: 0, unit: 'em', group: 'pose', precision: 3, snap: false },
  /** How far the lips part. Its own group because it FOLLOWS the shape of
   * the mouth rather than leading it — and because speech rides it. */
  mouthOpen: { rest: 0, unit: 'num', group: 'mouth', precision: 3, snap: false },
  /** Derived from `mouthCurve`: the DEPTH of the arc (always positive, in
   * em) and which way it bends. The stylesheet cannot take an absolute
   * value or a sign, so the rig hands it both — and it HOLDS the sign
   * through the flat crossing, or a mouth resting near zero would flicker
   * between a smile and a frown on numerical noise. */
  /** How deep the curve bends, 0 to 1 — UNITLESS on purpose. The
   * stylesheet turns it into a height AND into a corner radius, and a
   * length could do neither: CSS cannot divide one length by another, so a
   * depth in em can never become the ratio that flattens the top edge of a
   * grin. */
  mouthArc: { rest: 0, unit: 'num', group: 'mouth', precision: 3, snap: false, derived: true },
  mouthFlip: { rest: 1, unit: 'num', group: 'mouth', precision: 0, snap: true, derived: true },
  /** Velocity squash & stretch, at constant volume: `stretchK` is how much
   * the pair stretches ALONG its direction of travel, `stretchA` is that
   * direction. Derived from the gaze velocity every frame — an eye that
   * moves fast deforms, and one at rest does not. */
  stretchK: { rest: 0, unit: 'num', group: 'stretch', precision: 3, snap: false, derived: true },
  stretchA: { rest: 0, unit: 'deg', group: 'stretch', precision: 1, snap: false, derived: true },
} as const satisfies Record<string, ChannelSpec>;

const EYE_SPECS = {
  /** Pose scale. */
  sx: { rest: 1, unit: 'num', group: 'pose', precision: 4, snap: false },
  sy: { rest: 1, unit: 'num', group: 'pose', precision: 4, snap: false },
  /** Scale anchor, in percent of the eye box (100% = the TOP lid comes down). */
  oy: { rest: 50, unit: 'pct', group: 'pose', precision: 1, snap: true },
  /** Per-eye rotation — in this design language, the slant IS the brow. */
  rot: { rest: 0, unit: 'deg', group: 'pose', precision: 2, snap: false },
  /** The STYLE's own base tilt (the almond lean), separate from the
   * expression slant because it pivots the whole eye box rather than the
   * shape around its scale anchor. */
  baseRot: { rest: 0, unit: 'deg', group: 'pose', precision: 2, snap: false },
  tx: { rest: 0, unit: 'em', group: 'pose', precision: 3, snap: false },
  ty: { rest: 0, unit: 'em', group: 'pose', precision: 3, snap: false },
  /** Sustained lids: a curved clip COVERS an intact eye, never squashes it. */
  lidTop: { rest: 0, unit: 'pct', group: 'lid', precision: 1, snap: false },
  lidBot: { rest: 0, unit: 'pct', group: 'lid', precision: 1, snap: false },
  lidR: { rest: 0, unit: 'em', group: 'lid', precision: 3, snap: false },
  /** Blink closure, 0 (open) to 1 (shut) — composes with the sustained lids. */
  blink: { rest: 0, unit: 'num', group: 'blink', precision: 3, snap: false },
  /** The brow, an organ of its own — height above the eye, tilt, curvature
   * and how PRESENT it is. Height, tilt and curvature are `pose` (they are
   * willed, so they anticipate and exaggerate); presence is `aura` (it
   * follows).
   *
   * It is PRESENT at rest, faintly (ADR-264, reversing ADR-252). Ten of the
   * fourteen psyche moods idle on `neutral`, so a brow that only exists once
   * an emotion lands has nothing to do for most of the session — and when
   * an emotion does land it APPEARS, on a fade, rather than moving. A faint
   * resting brow is what the breath, the gaze coupling and the idle beats
   * have to act on. */
  browY: { rest: 0, unit: 'em', group: 'pose', precision: 3, snap: false },
  browRot: { rest: 0, unit: 'deg', group: 'pose', precision: 2, snap: false },
  browA: { rest: 0.5, unit: 'num', group: 'aura', precision: 3, snap: false },
  /** How much the brow CURVES, 0 (a bar) to 1 (a full arch) — unitless for
   * the same reason `mouthArc` is: the stylesheet needs it as a height AND
   * as a radius ratio. A bar can only tilt; an arch can wonder, and the
   * difference between the two is most of what a brow says. */
  browArc: { rest: 0.12, unit: 'num', group: 'pose', precision: 3, snap: false },
  /** Pupil dilation. Its own group because it is SECONDARY action: the
   * pupil reacts to the emotion, a beat after the face does. */
  pupil: { rest: 1, unit: 'num', group: 'organ', precision: 3, snap: false },
  /** Silhouette radii (horizontal / vertical, top / bottom edge). */
  rTop: { rest: 0.28, unit: 'em', group: 'radius', precision: 3, snap: false },
  rBot: { rest: 0.28, unit: 'em', group: 'radius', precision: 3, snap: false },
  rvTop: { rest: 0.28, unit: 'em', group: 'radius', precision: 3, snap: false },
  rvBot: { rest: 0.28, unit: 'em', group: 'radius', precision: 3, snap: false },
} as const satisfies Record<string, ChannelSpec>;

export type GlobalChannel = keyof typeof GLOBAL_SPECS;
export type EyeChannelBase = keyof typeof EYE_SPECS;
export type EyeSide = 'L' | 'R';
export type EyeChannel = `${EyeChannelBase}${EyeSide}`;
export type ChannelKey = GlobalChannel | EyeChannel;

/** Per-eye bases, for callers that need to walk both sides symmetrically. */
export const EYE_CHANNEL_BASES = Object.keys(EYE_SPECS) as readonly EyeChannelBase[];

/** camelCase channel name -> kebab custom-property fragment. */
function kebab(name: string): string {
  return name.replace(/[A-Z]/g, letter => `-${letter.toLowerCase()}`);
}

function buildChannels(): Record<ChannelKey, ChannelDef> {
  const table: Record<string, ChannelDef> = {};
  for (const [name, spec] of Object.entries(GLOBAL_SPECS)) {
    table[name] = { ...spec, cssVar: `--rig-${kebab(name)}` };
  }
  for (const [name, spec] of Object.entries(EYE_SPECS)) {
    for (const side of ['L', 'R'] as const) {
      table[`${name}${side}`] = {
        ...spec,
        cssVar: `--rig-${kebab(name)}-${side.toLowerCase()}`,
      };
    }
  }
  // The expansion is a loop, which TypeScript cannot type as the mapped
  // record; the shape is pinned by the sibling completeness test instead.
  return table as Record<ChannelKey, ChannelDef>;
}

export const CHANNELS: Record<ChannelKey, ChannelDef> = buildChannels();

/** Stable iteration order — the runtime's typed arrays index by position. */
export const CHANNEL_KEYS = Object.keys(CHANNELS) as readonly ChannelKey[];

/** A full set of channel values (targets, current pose, a golden frame…). */
export type ChannelValues = Record<ChannelKey, number>;

/** Partial set — what a pose or a style override declares. */
export type PartialChannelValues = Partial<ChannelValues>;

const UNIT_SUFFIX: Record<ChannelUnit, string> = {
  num: '',
  em: 'em',
  deg: 'deg',
  pct: '%',
};

/**
 * Serialize one channel value for the style attribute.
 *
 * Rounding to the channel precision is deliberate on two counts: it caps the
 * cost of the write loop (an unchanged string is not written) and it kills
 * the `-0` a signed rounding would otherwise produce, which would churn the
 * attribute on every frame of a settled channel.
 */
export function formatChannel(key: ChannelKey, value: number): string {
  const def = CHANNELS[key];
  const rounded = Number(value.toFixed(def.precision));
  const text = rounded === 0 ? '0' : String(rounded);
  return `${text}${UNIT_SUFFIX[def.unit]}`;
}

/** The neutral pose: every channel at its rest value. */
export function restChannelValues(): ChannelValues {
  const values: Record<string, number> = {};
  for (const key of CHANNEL_KEYS) values[key] = CHANNELS[key].rest;
  return values as ChannelValues;
}
