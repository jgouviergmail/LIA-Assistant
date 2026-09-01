/**
 * Dynamics — how an emotion ARRIVES, expressed as physics.
 *
 * The stylesheet this replaces encoded arrival as a duration plus a bezier
 * (650 ms base, 950 ms for the slow family, 500 ms for joy, 190 ms for a
 * reflex, 380 ms for anger). A spring says the same thing with two numbers
 * and keeps saying it when the motion is INTERRUPTED, which a transition
 * cannot: retargeting mid-flight preserves the velocity instead of restarting
 * from wherever the interpolation happened to be.
 *
 * The frequencies below are derived from those durations, not invented: a
 * critically damped spring covers 99 % of its travel in `1.057 / f` seconds,
 * so `f = 1.057 / t99`. The damping ratios are the art direction — joy rings,
 * anger lands hard, sadness drags in.
 *
 * A preset tunes GROUPS, never the forty-odd channels one by one, and the
 * group scales below ARE the overlapping-action rule: the gaze leads, the
 * mass follows, the lids trail. Nothing in an expressive face moves on the
 * same curve at the same time.
 */

import { CHANNELS, type ChannelGroup, type ChannelKey } from '@/components/eyes/rig/channels';
import type { EyeExpression, IdleMoodFamily } from '@/components/eyes/expression-engine';
import type { SpringConfig } from '@/components/eyes/rig/spring';

/** Settling time (99 % of travel) of a critically damped spring, in seconds. */
const CRITICAL_SETTLE_FACTOR = 1.057;

/** Frequency (Hz) whose critically damped settle time is `ms`. */
function frequencyForSettleMs(ms: number): number {
  return CRITICAL_SETTLE_FACTOR / (ms / 1000);
}

export type DynamicsName = 'base' | 'slow' | 'quick' | 'reflex' | 'strike';

/** One preset: a spring per channel group. */
export type Dynamics = Record<ChannelGroup, SpringConfig>;

/** Per-group frequency multipliers — the overlapping-action ladder.
 * The gaze arrives first (an eye moves before a face does), the lids trail
 * the pose, the mass is the slowest thing in the body, and the blink is an
 * order of magnitude faster than anything else it composes with. */
const GROUP_FREQUENCY_SCALE: Record<ChannelGroup, number> = {
  gaze: 1.35,
  pose: 1,
  lid: 0.82,
  blink: 3.2,
  mass: 0.7,
  radius: 0.78,
  aura: 0.6,
  // A pupil dilates slowly — it is the slowest thing on the face.
  organ: 0.72,
  // A mouth is quick — speech and laughter both live in it.
  mouth: 1.25,
  // Derived: computed from the motion, never sprung. Declared for
  // completeness so no channel can fall through the table.
  stretch: 1,
};

/** Per-group damping multipliers: the heavy parts must not wobble. */
const GROUP_DAMPING_SCALE: Record<ChannelGroup, number> = {
  gaze: 1,
  pose: 1,
  lid: 1.12,
  blink: 1,
  mass: 1.25,
  radius: 1.05,
  aura: 1.3,
  organ: 1.2,
  mouth: 0.9,
  stretch: 1,
};

/**
 * Overlapping action, the explicit half.
 *
 * The frequency ladder above already staggers the ARRIVALS; these delays
 * stagger the DEPARTURES. The split is the principle itself: what the face
 * WILLS (its pose, its mass) leaves immediately and is preceded by an
 * anticipation; what merely FOLLOWS (the lids, the silhouette, the light)
 * waits a beat before moving at all. A face whose every part starts on the
 * same frame reads as a diagram of an emotion rather than as an emotion.
 */
export const GROUP_LEAD_MS: Record<ChannelGroup, number> = {
  gaze: 0,
  pose: 0,
  mass: 0,
  blink: 0,
  stretch: 0,
  lid: 60,
  radius: 90,
  organ: 110,
  aura: 120,
  // The mouth follows the eyes by a beat: a face whose mouth and eyes
  // change on the same frame reads as a mask being swapped.
  mouth: 45,
};

/**
 * Per-CHANNEL lead, overriding the group's — the corners of a mouth move
 * before its curve does.
 *
 * This is not a refinement, it is how a smile is built. A real one starts at
 * the corners and the curve follows them; a mouth whose corners, width and
 * curve all depart on the same frame is a shape being replaced, not a face
 * changing its mind. The group mechanism could not express it because all
 * three live in `pose` — one group, one departure.
 *
 * The values are small on purpose. Past roughly a tenth of a second the parts
 * stop reading as one mouth.
 */
export const CHANNEL_LEAD_MS: Partial<Record<ChannelKey, number>> = {
  // The curve waits for the corners it is supposed to follow.
  mouthCurve: 70,
  // ...and the width waits a little less, so the mouth spreads INTO the curve
  // rather than arriving already spread.
  mouthW: 40,
};

/** The lead a channel actually gets: its own if it declares one, else its
 * group's. */
export function leadMsFor(key: ChannelKey): number {
  return CHANNEL_LEAD_MS[key] ?? GROUP_LEAD_MS[CHANNELS[key].group];
}

/**
 * Exaggeration, per mood family — the tenth principle, and the one that turns
 * the mood into something the body carries rather than a label. A lively LIA
 * moves further and faster; a drowsy one moves less and slower. Amplitude
 * scales the distance from the rest pose, frequency scales the springs.
 */
export const FAMILY_DYNAMICS: Record<IdleMoodFamily, { frequency: number; amplitude: number }> = {
  lively: { frequency: 1.12, amplitude: 1.06 },
  calm: { frequency: 1, amplitude: 1 },
  drowsy: { frequency: 0.82, amplitude: 0.92 },
};

const GROUPS = Object.keys(GROUP_FREQUENCY_SCALE) as readonly ChannelGroup[];

function preset(settleMs: number, damping: number): Dynamics {
  const base = frequencyForSettleMs(settleMs);
  const table: Record<string, SpringConfig> = {};
  for (const group of GROUPS) {
    table[group] = {
      frequency: base * GROUP_FREQUENCY_SCALE[group],
      damping: damping * GROUP_DAMPING_SCALE[group],
    };
  }
  return table as Dynamics;
}

/**
 * The five arrival dynamics.
 *  - `base`   — the unhurried default, a whisper of overshoot
 *  - `slow`   — sadness and drowsiness: heavy, no bounce, it settles INTO the
 *               pose rather than reaching it
 *  - `quick`  — joy and excitement: a real spring, it rings
 *  - `strike` — anger: fast and absolutely rigid. A scowl that wobbles is
 *               comic, and anger is the one emotion that must not be
 *  - `reflex` — surprise and fear: the fastest thing the face can do
 */
export const DYNAMICS: Record<DynamicsName, Dynamics> = {
  base: preset(650, 0.86),
  slow: preset(950, 1.05),
  quick: preset(500, 0.55),
  strike: preset(380, 1),
  reflex: preset(190, 0.78),
};

/** Which dynamic each expression lands with — the CSS arrival table, kept. */
export const DYNAMICS_FOR_EXPRESSION: Record<EyeExpression, DynamicsName> = {
  neutral: 'base',
  joy: 'quick',
  excited: 'quick',
  tender: 'base',
  surprise: 'reflex',
  fear: 'reflex',
  anger: 'strike',
  sad: 'slow',
  worried: 'base',
  question: 'base',
  thinking: 'base',
  searching: 'base',
  focused: 'base',
  attentive: 'quick',
  speaking: 'base',
  bored: 'slow',
  tired: 'slow',
  sleepy: 'slow',
  sleep: 'slow',
  wink: 'quick',
};

/** The spring one channel uses while an expression is on screen. */
export function dynamicsFor(expression: EyeExpression, channel: ChannelKey): SpringConfig {
  return DYNAMICS[DYNAMICS_FOR_EXPRESSION[expression]][CHANNELS[channel].group];
}
