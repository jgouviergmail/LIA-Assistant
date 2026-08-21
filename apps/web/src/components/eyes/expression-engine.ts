/**
 * Expression engine for the expressive-eyes widget — pure decision tables.
 *
 * Everything here is deterministic and side-effect free: the widget feeds the
 * current signals in, the engine answers "which expression, looking where".
 * Randomness (blink cadence, double blinks) takes an injected RNG so tests
 * stay exact. Same doctrine as `deriveCompanionState` (CompanionPresence) and
 * the chat reducer: behavior lives in pure functions, React only wires them.
 *
 * Priority chain (highest first — pinned by the test matrix):
 *   error > HITL question > voice (recording/processing/speaking)
 *   > interaction (sending/compacting/streaming) > post-response reaction
 *   > notification ping > user typing > inactivity stages > idle (mood x hour)
 */

import type { MoodLabel } from '@/types/psyche';
import type { VoiceModeState } from '@/stores/voiceModeStore';

// =============================================================================
// Vocabulary
// =============================================================================

/** The rendering vocabulary: every value maps to one CSS expression recipe. */
export type EyeExpression =
  | 'neutral'
  | 'joy'
  | 'excited'
  | 'tender'
  | 'surprise'
  | 'fear'
  | 'anger'
  | 'sad'
  | 'worried'
  | 'question'
  | 'thinking'
  | 'searching'
  | 'focused'
  | 'attentive'
  | 'speaking'
  | 'bored'
  | 'tired'
  | 'sleepy'
  | 'sleep'
  | 'wink';

/** Normalized gaze offset: x/y in [-1, 1], (0, 0) = straight ahead. */
export interface Gaze {
  x: number;
  y: number;
}

/** What the widget renders: an expression, optionally looking somewhere. */
export interface ExpressionFrame {
  expression: EyeExpression;
  /** Directed gaze, or null to leave the gaze to the idle drift/parallax. */
  gaze: Gaze | null;
}

/** 0 = active, 1 = drowsy, 2 = sleepy, 3 = asleep. */
export type InactivityStage = 0 | 1 | 2 | 3;

/** Live signals the widget gathers each evaluation. */
export interface ExpressionInputs {
  chatStatus: 'idle' | 'sending' | 'streaming' | 'error' | 'compacting';
  streamPhase: 'progress' | 'answer';
  /** Kind of the latest execution step, only meaningful during 'progress'. */
  lastStepKind: 'reasoning' | 'tool' | null;
  hitlAwaiting: boolean;
  voiceState: VoiceModeState;
  /** Held post-response reaction (already resolved via deriveReaction). */
  reaction: EyeExpression | null;
  /** A proactive notification landed moments ago. */
  notificationPing: boolean;
  /** The user is typing in the chat input right now. */
  userTyping: boolean;
  /** Live psyche mood, or null when psyche is disabled (graceful fallback). */
  moodLabel: MoodLabel | null;
  /** Local hour of day [0, 23]. */
  hourOfDay: number;
  inactivityStage: InactivityStage;
}

// =============================================================================
// Timing constants (idle loop + reaction hold)
// =============================================================================

/* Blink cadence: research on robot eyes places perceived aliveness around a
 * 2-3 s mean inter-blink interval — the old 2.6-6.2 s band read sluggish.
 * The band is per-family now (FAMILY_BLINK_RANGE_MS); these two constants
 * remain the 'calm' reference band. */
export const BLINK_MIN_DELAY_MS = 2200;
export const BLINK_MAX_DELAY_MS = 4800;
/** Chance that a blink is a quick double blink. */
export const DOUBLE_BLINK_PROBABILITY = 0.12;
/** One blink cycle length — MUST match the `lia-eye-blink` CSS duration. */
export const BLINK_DURATION_MS = 420;
/** Pause between the two cycles of a double blink. */
export const DOUBLE_BLINK_GAP_MS = 160;
/** How long the worried look is held after a turn fails before easing back. */
export const ERROR_HOLD_MS = 10_000;
/** One-shot wink length before reverting to the derived expression. */
export const WINK_DURATION_MS = 900;

/** Progressive dozing-off thresholds (ms since the last user activity). */
export const INACTIVITY_DROWSY_MS = 4 * 60 * 1000;
export const INACTIVITY_SLEEPY_MS = 8 * 60 * 1000;
export const INACTIVITY_ASLEEP_MS = 15 * 60 * 1000;

/** How long a post-response reaction is held before easing back to idle. */
export const REACTION_HOLD_MS = 4000;
/** How long a notification ping holds the surprised glance. */
export const NOTIFICATION_PING_MS = 2500;
/** Typing is considered live for this long after the last keystroke. */
export const TYPING_ACTIVE_MS = 1800;
/** Minimum self-report intensity for an emotion to drive the reaction. */
export const REACTION_EMOTION_MIN_INTENSITY = 0.25;

// =============================================================================
// Directed gazes (scene geography: input below, toasts top-right)
// =============================================================================

const GAZE_INPUT: Gaze = { x: 0, y: 1 };
const GAZE_THINKING: Gaze = { x: -0.6, y: -1 };
const GAZE_TOAST: Gaze = { x: 1, y: -1 };

// =============================================================================
// Main derivation
// =============================================================================

/** Expression while the pipeline streams, split by phase and step kind. */
function streamingExpression(inputs: ExpressionInputs): ExpressionFrame {
  if (inputs.streamPhase === 'progress') {
    if (inputs.lastStepKind === 'tool') {
      return { expression: 'searching', gaze: null };
    }
    return { expression: 'thinking', gaze: GAZE_THINKING };
  }
  return { expression: 'speaking', gaze: null };
}

/** Idle base: psyche mood first, hour-of-day bias when mood is absent/neutral. */
function idleExpression(inputs: ExpressionInputs): ExpressionFrame {
  const moodExpression = inputs.moodLabel ? moodToIdleExpression(inputs.moodLabel) : 'neutral';
  if (moodExpression !== 'neutral') {
    return { expression: moodExpression, gaze: null };
  }
  const band = hourBand(inputs.hourOfDay);
  if (band === 'night') {
    return { expression: 'sleepy', gaze: null };
  }
  if (band === 'morning') {
    return { expression: 'attentive', gaze: null };
  }
  return { expression: 'neutral', gaze: null };
}

/**
 * Derive the frame to render from the current signals.
 *
 * Pure and total: every combination of inputs resolves to exactly one frame,
 * following the documented priority chain.
 */
export function deriveExpression(inputs: ExpressionInputs): ExpressionFrame {
  if (inputs.chatStatus === 'error') {
    return { expression: 'worried', gaze: null };
  }
  if (inputs.hitlAwaiting) {
    return { expression: 'question', gaze: null };
  }
  if (inputs.voiceState === 'recording') {
    return { expression: 'attentive', gaze: null };
  }
  if (inputs.voiceState === 'processing') {
    return { expression: 'thinking', gaze: GAZE_THINKING };
  }
  if (inputs.voiceState === 'speaking') {
    return { expression: 'speaking', gaze: null };
  }
  if (inputs.chatStatus === 'sending') {
    return { expression: 'attentive', gaze: GAZE_INPUT };
  }
  if (inputs.chatStatus === 'compacting') {
    return { expression: 'focused', gaze: null };
  }
  if (inputs.chatStatus === 'streaming') {
    return streamingExpression(inputs);
  }
  if (inputs.reaction) {
    return { expression: inputs.reaction, gaze: null };
  }
  if (inputs.notificationPing) {
    return { expression: 'surprise', gaze: GAZE_TOAST };
  }
  if (inputs.userTyping) {
    return { expression: 'attentive', gaze: GAZE_INPUT };
  }
  if (inputs.inactivityStage === 3) {
    return { expression: 'sleep', gaze: null };
  }
  if (inputs.inactivityStage === 2) {
    return { expression: 'sleepy', gaze: null };
  }
  if (inputs.inactivityStage === 1) {
    return { expression: 'tired', gaze: null };
  }
  return idleExpression(inputs);
}

// =============================================================================
// Psyche mappings
// =============================================================================

/** Post-response emotion (psyche self-report vocabulary) → expression. */
const EMOTION_EXPRESSIONS: Record<string, EyeExpression> = {
  joy: 'joy',
  gratitude: 'tender',
  pride: 'joy',
  amusement: 'joy',
  enthusiasm: 'excited',
  tenderness: 'tender',
  playfulness: 'joy',
  relief: 'joy',
  wonder: 'surprise',
  frustration: 'anger',
  concern: 'worried',
  melancholy: 'sad',
  disappointment: 'sad',
  nervousness: 'fear',
  curiosity: 'attentive',
  serenity: 'neutral',
  surprise: 'surprise',
  empathy: 'tender',
  confusion: 'question',
  determination: 'focused',
  protectiveness: 'focused',
  resolve: 'focused',
};

/** Map a psyche emotion name to an eye expression (neutral on unknown). */
export function emotionToExpression(emotion: string): EyeExpression {
  return EMOTION_EXPRESSIONS[emotion] ?? 'neutral';
}

/**
 * Idle baseline for each of the 14 canonical psyche moods.
 *
 * Deliberately SOFT (owner arbitration 2026-08-21): the resting pose is the
 * character's identity card, so idle only uses the readable base silhouettes
 * (neutral / attentive / thinking). Strong poses (joy, focused, tender,
 * sad...) are temporal ACCENTS — per-turn reactions, notifications,
 * execution phases — never a held resting state; a permanently squinted
 * standby read as unsettling and hid the selected eye style. The mood's
 * personality lives in the GESTURE family instead (MOOD_IDLE_FAMILIES).
 */
const MOOD_IDLE_EXPRESSIONS: Record<MoodLabel, EyeExpression> = {
  serene: 'neutral',
  curious: 'attentive',
  energized: 'attentive',
  playful: 'attentive',
  reflective: 'thinking',
  agitated: 'neutral',
  melancholic: 'neutral',
  neutral: 'neutral',
  content: 'neutral',
  determined: 'neutral',
  defiant: 'neutral',
  resigned: 'neutral',
  overwhelmed: 'neutral',
  tender: 'neutral',
};

/**
 * Gesture family carried by each mood while idling — the personality channel
 * that replaced the strong resting poses: lively moods keep their bounces
 * and pranks, low moods their slow blinks, on an intact silhouette.
 */
const MOOD_IDLE_FAMILIES: Record<MoodLabel, IdleMoodFamily> = {
  serene: 'calm',
  curious: 'lively',
  energized: 'lively',
  playful: 'lively',
  reflective: 'calm',
  agitated: 'lively',
  melancholic: 'drowsy',
  neutral: 'calm',
  content: 'calm',
  determined: 'calm',
  defiant: 'lively',
  resigned: 'drowsy',
  overwhelmed: 'drowsy',
  tender: 'calm',
};

/** Gesture family for a mood while idling (see MOOD_IDLE_FAMILIES). */
export function idleFamilyForMood(mood: MoodLabel): IdleMoodFamily {
  return MOOD_IDLE_FAMILIES[mood];
}

/** Map a psyche mood label to the idle-loop baseline expression. */
export function moodToIdleExpression(mood: MoodLabel): EyeExpression {
  return MOOD_IDLE_EXPRESSIONS[mood];
}

// =============================================================================
// Post-response reaction (per-turn self-report first, heuristic fallback)
// =============================================================================

export interface ReactionSource {
  /** `active_emotions` from the done psyche snapshot (null: absent/disabled). */
  psycheEmotions: Array<{ name: string; intensity: number }> | null;
  /** Final response text (already rendered to the user). */
  content: string;
  /** The turn ended in an error bubble. */
  isError: boolean;
  /** The turn produced generated images/documents cards. */
  hasArtifacts: boolean;
}

/**
 * Resolve the post-response reaction.
 *
 * The per-turn psyche self-report (the LLM appraising its own exchange) is
 * the primary signal; when it is absent — psyche disabled, or the
 * fire-and-forget update lost the race with the SSE done — a language-neutral
 * content heuristic takes over. Returns null when nothing is worth reacting to.
 */
export function deriveReaction(source: ReactionSource): EyeExpression | null {
  const top = source.psycheEmotions?.[0];
  if (top && top.intensity >= REACTION_EMOTION_MIN_INTENSITY) {
    return emotionToExpression(top.name);
  }
  return contentHeuristicExpression(source);
}

// Emoji classes — deliberately short, high-precision lists. Punctuation and
// emoji are the only signals: no word matching, so all 6 locales behave
// identically (zh included via fullwidth ？ and ！).
const JOY_EMOJI = /[😀😃😄😁😊🙂😍🥰🤩🎉🎊✨🌟⭐❤🧡💛💚💙💜👍🥳💪🚀]/u;
const SAD_EMOJI = /[😢😭😞😔☹🙁💔😿]/u;
const SURPRISE_EMOJI = /[😮😲😯🤯]/u;

/** Strip fenced code blocks so their contents never drive punctuation cues. */
function withoutCodeFences(content: string): string {
  return content.replace(/```[\s\S]*?(?:```|$)/g, ' ');
}

/**
 * Language-neutral reaction heuristic over the final response.
 *
 * Order: error > artifacts > emoji > trailing question > double exclamation
 * > code fence > null. Every cue is punctuation/emoji/structure — never words.
 */
export function contentHeuristicExpression(source: {
  content: string;
  isError: boolean;
  hasArtifacts: boolean;
}): EyeExpression | null {
  if (source.isError) return 'worried';
  if (source.hasArtifacts) return 'joy';

  const text = withoutCodeFences(source.content);
  if (JOY_EMOJI.test(text)) return 'joy';
  if (SAD_EMOJI.test(text)) return 'sad';
  if (SURPRISE_EMOJI.test(text)) return 'surprise';
  if (/[?？]\s*$/.test(text)) return 'question';
  if ((text.match(/[!！]/g) ?? []).length >= 2) return 'excited';
  if (/```/.test(source.content)) return 'focused';
  return null;
}

// =============================================================================
// Inactivity staging & hour bands
// =============================================================================

/** Progressive dozing-off stage for the elapsed idle time. */
export function inactivityStageFor(msSinceActivity: number): InactivityStage {
  if (msSinceActivity >= INACTIVITY_ASLEEP_MS) return 3;
  if (msSinceActivity >= INACTIVITY_SLEEPY_MS) return 2;
  if (msSinceActivity >= INACTIVITY_DROWSY_MS) return 1;
  return 0;
}

export type HourBand = 'night' | 'morning' | 'day';

/** Coarse day segmentation for the idle bias (22h-6h night, 6h-10h morning). */
export function hourBand(hour: number): HourBand {
  if (hour >= 22 || hour < 6) return 'night';
  if (hour < 10) return 'morning';
  return 'day';
}

// =============================================================================
// Idle scheduling (RNG injected)
// =============================================================================

export type Rng = () => number;

/** Spontaneous-blink cadence band per mood family — livelier moods blink
 * more often (alertness), drowsy ones slower and rarer. */
export const FAMILY_BLINK_RANGE_MS: Record<IdleMoodFamily, readonly [number, number]> = {
  lively: [1900, 4200],
  calm: [BLINK_MIN_DELAY_MS, BLINK_MAX_DELAY_MS],
  drowsy: [3000, 6500],
};

/** Delay until the next spontaneous blink, paced by the mood family. */
export function nextBlinkDelayMs(rng: Rng, family: IdleMoodFamily = 'calm'): number {
  const [min, max] = FAMILY_BLINK_RANGE_MS[family];
  return Math.round(min + rng() * (max - min));
}

/** Whether the upcoming blink is a quick double blink. */
export function isDoubleBlink(rng: Rng): boolean {
  return rng() < DOUBLE_BLINK_PROBABILITY;
}

// =============================================================================
// Idle life — the random gesture library that keeps the eyes alive between
// events. Everything is RNG-injected; the hook only schedules what these
// tables decide. Gaze wander (saccade/glance) and one-shot gestures are the
// two channels; both are weighted by the current mood family so personality
// stays coherent (a drowsy LIA never bounces, an excited one never yawns).
// =============================================================================

/** Random pause between two idle gestures — lively but never twitchy. */
export const IDLE_GESTURE_MIN_DELAY_MS = 1900;
export const IDLE_GESTURE_MAX_DELAY_MS = 5600;

/** Rare slapstick beats — comedy, not physiology. Awake families only. */
export type SillyGesture =
  | 'swap' // the eyes trade places in a little circus arc, then trade back
  | 'bump' // drift apart, rush together, CLACK with a squash, rebound
  | 'spin' // quick 360° pirouette, right eye trailing
  | 'jelly'; // wobbly jello shudder that settles

export type IdleGesture =
  | 'saccade' // quick small gaze jump (dominant — real eyes never sit still)
  | 'glance' // wide gaze excursion, held, then back to center
  | 'slow-blink' // languid blink (drowsy signature)
  | 'half-blink' // partial lid drop
  | 'squint' // brief squint-and-release
  | 'tilt' // small head-tilt wobble
  | 'bounce' // happy little hop (lively signature)
  | 'perk' // quick attention scale-flick
  | 'brow' // asymmetric single-brow raise (awake families only)
  | 'flicker' // a mini mood scene (ponder, interest, daydream — see IDLE_FLICKERS)
  | SillyGesture;

export const SILLY_GESTURES: readonly SillyGesture[] = ['swap', 'bump', 'spin', 'jelly'];

/** Chance that an idle tick plays a slapstick beat instead of a normal one —
 * roughly one per minute of quiet idling. Rarity IS the joke. */
export const SILLY_PROBABILITY = 0.06;

/** Whether this idle tick goes slapstick. */
export function isSillyTime(rng: Rng): boolean {
  return rng() < SILLY_PROBABILITY;
}

/** Pick one slapstick beat, uniformly. */
export function pickSillyGesture(rng: Rng): SillyGesture {
  return SILLY_GESTURES[
    Math.min(SILLY_GESTURES.length - 1, Math.floor(rng() * SILLY_GESTURES.length))
  ];
}

/** Expressions that run the idle-life loop at all. */
export const IDLE_LIFE_EXPRESSIONS: ReadonlySet<EyeExpression> = new Set([
  'neutral',
  'attentive',
  'joy',
  'excited',
  'tender',
  'bored',
  'tired',
  'sleepy',
]);

export type IdleMoodFamily = 'lively' | 'calm' | 'drowsy';

/** Mood family of an idle-capable expression (calm for anything else). */
export function idleFamilyFor(expression: EyeExpression): IdleMoodFamily {
  if (expression === 'joy' || expression === 'excited' || expression === 'attentive') {
    return 'lively';
  }
  if (expression === 'tired' || expression === 'sleepy') {
    return 'drowsy';
  }
  return 'calm';
}

/** Per-family gesture weights — the personality table. */
const FAMILY_GESTURE_WEIGHTS: Record<IdleMoodFamily, ReadonlyArray<[IdleGesture, number]>> = {
  lively: [
    ['saccade', 0.3],
    ['glance', 0.12],
    ['perk', 0.1],
    ['bounce', 0.11],
    ['half-blink', 0.08],
    ['tilt', 0.08],
    ['squint', 0.07],
    ['brow', 0.06],
    ['flicker', 0.08],
  ],
  calm: [
    ['saccade', 0.36],
    ['glance', 0.15],
    ['half-blink', 0.08],
    ['tilt', 0.08],
    ['squint', 0.07],
    ['slow-blink', 0.08],
    ['perk', 0.05],
    ['brow', 0.05],
    ['flicker', 0.08],
  ],
  drowsy: [
    ['slow-blink', 0.38],
    ['half-blink', 0.22],
    ['saccade', 0.2],
    ['glance', 0.12],
    ['squint', 0.08],
  ],
};

/** Delay until the next idle gesture. */
export function nextIdleGestureDelayMs(rng: Rng): number {
  return Math.round(
    IDLE_GESTURE_MIN_DELAY_MS + rng() * (IDLE_GESTURE_MAX_DELAY_MS - IDLE_GESTURE_MIN_DELAY_MS)
  );
}

/**
 * Resolve the idle gesture family: the psyche mood is the primary personality
 * channel (soft resting poses carry no mood of their own — see
 * MOOD_IDLE_FAMILIES); the expression is the fallback when psyche is off.
 */
export function resolveIdleFamily(
  mood: MoodLabel | null,
  expression: EyeExpression
): IdleMoodFamily {
  return mood ? idleFamilyForMood(mood) : idleFamilyFor(expression);
}

/** Pick the next idle gesture from the family's personality weights. */
export function pickIdleGesture(rng: Rng, family: IdleMoodFamily): IdleGesture {
  const weights = FAMILY_GESTURE_WEIGHTS[family];
  const total = weights.reduce((sum, [, w]) => sum + w, 0);
  let cursor = rng() * total;
  for (const [gesture, weight] of weights) {
    cursor -= weight;
    if (cursor < 0) return gesture;
  }
  return weights[weights.length - 1][0];
}

/** How long a one-shot gesture holds its class — covers the CSS animation
 * (right-eye delays included) so clearing never snaps mid-motion. */
export const GESTURE_DURATION_MS: Record<
  Exclude<IdleGesture, 'saccade' | 'glance' | 'flicker'>,
  number
> = {
  'slow-blink': 1000,
  'half-blink': 420,
  squint: 800,
  tilt: 1000,
  bounce: 780,
  perk: 600,
  brow: 700,
  swap: 1800,
  bump: 1550,
  spin: 1200,
  jelly: 1250,
};

/** Gaze travel times: a saccade is quick (but readable), a glance sweeps. */
export const SACCADE_MOVE_MS = 140;
export const GLANCE_MOVE_MS = 260;
/** Ease-back to center after the hold — unhurried. */
export const GAZE_RETURN_MS = 650;
export const SACCADE_HOLD_MIN_MS = 350;
export const SACCADE_HOLD_MAX_MS = 1200;
export const GLANCE_HOLD_MIN_MS = 700;
export const GLANCE_HOLD_MAX_MS = 1600;

/** How long the wandered gaze is held before easing back to center. */
export function gazeHoldMs(rng: Rng, kind: 'saccade' | 'glance'): number {
  const [min, max] =
    kind === 'saccade'
      ? [SACCADE_HOLD_MIN_MS, SACCADE_HOLD_MAX_MS]
      : [GLANCE_HOLD_MIN_MS, GLANCE_HOLD_MAX_MS];
  return Math.round(min + rng() * (max - min));
}

/**
 * Random wander target. Saccades stay small and mostly horizontal (real eye
 * behavior); glances commit to a side with a wide horizontal excursion.
 */
export function idleGazeTarget(rng: Rng, kind: 'saccade' | 'glance'): Gaze {
  if (kind === 'saccade') {
    return { x: (rng() * 2 - 1) * 0.35, y: (rng() * 2 - 1) * 0.22 };
  }
  const side = rng() < 0.5 ? -1 : 1;
  return { x: side * (0.5 + rng() * 0.35), y: (rng() * 2 - 1) * 0.25 };
}

/** Chance that a glance chains to the opposite side before returning —
 * the "scanning the room" composite beat. */
export const GLANCE_CHAIN_PROBABILITY = 0.3;

/** Whether this glance sweeps to the other side before coming home. */
export function shouldChainGlance(rng: Rng): boolean {
  return rng() < GLANCE_CHAIN_PROBABILITY;
}

// =============================================================================
// Emotes — the little floating glyph above the eyes that makes an expression
// explicit ('?', '!', drifting 'z', thinking '…'). Pure mapping; the hook
// owns the enter/leave lifecycle, the CSS owns the animations.
// =============================================================================

/** How long the leave animation gets before the emote unmounts. */
export const EMOTE_EXIT_MS = 260;

const EXPRESSION_EMOTES: Partial<Record<EyeExpression, string>> = {
  question: '?',
  surprise: '!',
  sleep: 'z',
  thinking: '…',
};

/** Floating glyph for an expression, or null when the eyes speak alone. */
export function emoteForExpression(expression: EyeExpression): string | null {
  return EXPRESSION_EMOTES[expression] ?? null;
}

// =============================================================================
// Performances — short scripted multi-beat sequences for character-defining
// moments. Pure data: the hook plays the steps on its own timers.
// =============================================================================

export interface PerformanceStep {
  expression: EyeExpression;
  gaze: Gaze | null;
  /** How long this beat holds before the next step. */
  ms: number;
}

/**
 * Waking up is a startle, not a fade: jolt wide, check left, check right,
 * settle. Triggered when user activity lands while the eyes were dozing.
 */
/**
 * Idle mood flickers — mini scenes the quiet loop draws from so standby never
 * repeats itself: a pondering drift, a spark of interest, a daydream. Every
 * scene settles back to a free gaze (last step gaze: null).
 */
export const IDLE_FLICKERS: readonly (readonly PerformanceStep[])[] = [
  [
    { expression: 'thinking', gaze: { x: -0.5, y: -0.9 }, ms: 1100 },
    { expression: 'neutral', gaze: null, ms: 350 },
  ],
  [
    { expression: 'attentive', gaze: { x: 0.35, y: -0.3 }, ms: 900 },
    { expression: 'neutral', gaze: null, ms: 300 },
  ],
  [
    { expression: 'tender', gaze: { x: 0.2, y: 0.2 }, ms: 1300 },
    { expression: 'neutral', gaze: null, ms: 350 },
  ],
];

/** Pick one idle flicker scene, uniformly. */
export function pickIdleFlicker(rng: Rng): readonly PerformanceStep[] {
  return IDLE_FLICKERS[
    Math.min(IDLE_FLICKERS.length - 1, Math.floor(rng() * IDLE_FLICKERS.length))
  ];
}

export const WAKE_PERFORMANCE: readonly PerformanceStep[] = [
  { expression: 'surprise', gaze: null, ms: 480 },
  { expression: 'attentive', gaze: { x: -0.55, y: -0.1 }, ms: 430 },
  { expression: 'attentive', gaze: { x: 0.55, y: -0.1 }, ms: 430 },
  { expression: 'neutral', gaze: null, ms: 320 },
];

/**
 * Waking from a SHORT nap is a quick recollection, not a startle: a beat of
 * attention, then back to the room. The full WAKE_PERFORMANCE is reserved
 * for deep sleep (past SHORT_NAP_MS) — the reaction tells how long the eyes
 * were gone.
 */
export const SHORT_NAP_MS = 120_000;
export const WAKE_SHORT_PERFORMANCE: readonly PerformanceStep[] = [
  { expression: 'attentive', gaze: null, ms: 320 },
  { expression: 'neutral', gaze: null, ms: 260 },
];

/** Which wake performance a doze of `sleptMs` deserves. */
export function wakePerformanceFor(sleptMs: number): readonly PerformanceStep[] {
  return sleptMs >= SHORT_NAP_MS ? WAKE_PERFORMANCE : WAKE_SHORT_PERFORMANCE;
}

// =============================================================================
// Transition grammar — cognitive-boundary blinks, minimum holds, mood beats
// =============================================================================

/**
 * Humans blink right BEFORE moving their gaze (a cognitive boundary), not
 * during. A fraction of wanders opens with a blink whose lid covers the
 * saccade start — each move then reads as intentional.
 */
export const PRE_GAZE_BLINK_PROBABILITY = 0.4;
export const PRE_GAZE_BLINK_LEAD_MS = 130;

/** Whether the upcoming gaze wander opens with a blink. */
export function shouldBlinkBeforeGaze(rng: Rng): boolean {
  return rng() < PRE_GAZE_BLINK_PROBABILITY;
}

/**
 * Masked transitions land the new face at the TOP of the lid sweep (lids
 * closed) instead of alongside it — the morph happens out of sight, the
 * classical three-beat: blink, swap, reveal.
 */
export const MASK_APPLY_DELAY_MS = 140;

/**
 * Anti-zapping: a non-urgent expression holds at least this long before the
 * next one may replace it, so a burst of signals (stream end + notification)
 * never flickers the face. Urgent arrivals bypass the hold — a reflex that
 * waits is not a reflex.
 */
export const MIN_EXPRESSION_HOLD_MS = 400;
export const URGENT_ARRIVALS: ReadonlySet<EyeExpression> = new Set([
  'worried',
  'question',
  'surprise',
  'fear',
  'wink',
  'attentive',
  'speaking',
]);

/** Family rank used to read a mood change as rising or falling energy. */
const FAMILY_ENERGY: Record<IdleMoodFamily, number> = { drowsy: 0, calm: 1, lively: 2 };

/** Rising mood: a spark — double-take up, settle. */
export const MOOD_SHIFT_RISE_PERFORMANCE: readonly PerformanceStep[] = [
  { expression: 'attentive', gaze: { x: 0, y: -0.4 }, ms: 380 },
  { expression: 'joy', gaze: null, ms: 460 },
  { expression: 'neutral', gaze: null, ms: 300 },
];

/** Falling mood: a slow settle — the gaze drops, the lids ease. */
export const MOOD_SHIFT_FALL_PERFORMANCE: readonly PerformanceStep[] = [
  { expression: 'tired', gaze: { x: 0, y: 0.35 }, ms: 620 },
  { expression: 'neutral', gaze: null, ms: 380 },
];

/**
 * The beat played when the psyche mood shifts across families while idling —
 * an internal state change becomes a readable event instead of a silent
 * morph. Same-family shifts stay silent (the gesture cadence already moved).
 */
export function moodShiftPerformance(
  prev: MoodLabel,
  next: MoodLabel
): readonly PerformanceStep[] | null {
  const delta = FAMILY_ENERGY[idleFamilyForMood(next)] - FAMILY_ENERGY[idleFamilyForMood(prev)];
  if (delta > 0) return MOOD_SHIFT_RISE_PERFORMANCE;
  if (delta < 0) return MOOD_SHIFT_FALL_PERFORMANCE;
  return null;
}

// =============================================================================
// Reading pattern — the eyes "write" their streaming answer
// =============================================================================

/**
 * While the answer streams, the gaze walks a reading line (left to right in
 * small steps, quick carriage return) instead of random saccades — the most
 * watched moment of the widget gets its own choreography. The line sits
 * slightly UP: new text lands above the input-docked widget.
 */
const READING_LINE: readonly Gaze[] = [
  { x: -0.55, y: -0.35 },
  { x: -0.18, y: -0.35 },
  { x: 0.2, y: -0.35 },
  { x: 0.58, y: -0.35 },
];
export const READING_STEP_MS = 340;
export const READING_MOVE_MS = 120;
export const READING_RETURN_MS = 180;

/** Gaze move for reading beat `step` (cycles the line; step 0 is the quick
 * carriage return to line start). */
export function readingGazeAt(step: number): { gaze: Gaze; ms: number } {
  const index = ((step % READING_LINE.length) + READING_LINE.length) % READING_LINE.length;
  return { gaze: READING_LINE[index], ms: index === 0 ? READING_RETURN_MS : READING_MOVE_MS };
}

// =============================================================================
// Conversational micro-moments
// =============================================================================

/**
 * The user typed, then paused without sending: after the typing signal
 * expires the eyes come up from the input and wonder — "you were saying?".
 */
export const WONDER_PERFORMANCE: readonly PerformanceStep[] = [
  { expression: 'attentive', gaze: { x: 0, y: 0 }, ms: 520 },
  { expression: 'question', gaze: null, ms: 900 },
];

/**
 * Coming back to the tab after a real absence earns a small welcome perk —
 * awake families only (a drowsy character does not jump to attention).
 */
export const RETURN_PERK_MIN_AWAY_MS = 30_000;
