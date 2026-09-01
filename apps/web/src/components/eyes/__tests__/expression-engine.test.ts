/**
 * Expression engine — exhaustive behavioral matrix.
 *
 * The engine is a pure decision table: every test drives `deriveExpression`
 * (or one of its pure helpers) with explicit inputs and asserts the exact
 * expression, so the full priority chain is pinned:
 *
 *   error > HITL > voice > interaction > reaction > notification > typing
 *   > inactivity > idle (mood x hour)
 *
 * No timers, no DOM, no randomness (RNG is injected) — deliberately immune
 * to the jsdom `animationend` trap.
 */

import { describe, it, expect } from 'vitest';

import type { MoodLabel } from '@/types/psyche';

import {
  deriveExpression,
  moodToIdleExpression,
  idleFamilyForMood,
  resolveIdleFamily,
  inactivityStageFor,
  hourBand,
  nextBlinkDelayMs,
  isDoubleBlink,
  nextIdleGestureDelayMs,
  pickIdleGesture,
  idleFamilyFor,
  idleGazeTarget,
  gazeHoldMs,
  shouldChainGlance,
  WAKE_PERFORMANCE,
  PRE_GAZE_BLINK_PROBABILITY,
  PRE_GAZE_BLINK_LEAD_MS,
  BLINK_DURATION_MS,
  URGENT_ARRIVALS,
  MIN_EXPRESSION_HOLD_MS,
  MASK_APPLY_DELAY_MS,
  moodShiftPerformance,
  MOOD_SHIFT_RISE_PERFORMANCE,
  MOOD_SHIFT_FALL_PERFORMANCE,
  readingGazeAt,
  READING_MOVE_MS,
  READING_RETURN_MS,
  wakePerformanceFor,
  SHORT_NAP_MS,
  WAKE_SHORT_PERFORMANCE,
  shouldBlinkBeforeGaze,
  isSillyTime,
  pickSillyGesture,
  pickIdleFlicker,
  IDLE_FLICKERS,
  emoteForExpression,
  SILLY_GESTURES,
  SILLY_PROBABILITY,
  GESTURE_DURATION_MS,
  IDLE_GESTURE_MIN_DELAY_MS,
  IDLE_GESTURE_MAX_DELAY_MS,
  SACCADE_HOLD_MIN_MS,
  GLANCE_HOLD_MAX_MS,
  INACTIVITY_DROWSY_MS,
  INACTIVITY_SLEEPY_MS,
  INACTIVITY_ASLEEP_MS,
  BLINK_MIN_DELAY_MS,
  BLINK_MAX_DELAY_MS,
  type ExpressionInputs,
  ACCESSORY_DURATION_MS,
  EYE_EXPRESSIONS,
  accessoryForExpression,
  type Rng,
} from '../expression-engine';

/** Baseline inputs: an idle chat, psyche off, daytime, user active. */
function inputs(overrides: Partial<ExpressionInputs> = {}): ExpressionInputs {
  return {
    chatStatus: 'idle',
    streamPhase: 'answer',
    lastStepKind: null,
    hitlAwaiting: false,
    voiceState: 'idle',
    reaction: null,
    notificationPing: false,
    userTyping: false,
    moodLabel: null,
    hourOfDay: 14,
    inactivityStage: 0,
    ...overrides,
  };
}

// ---------------------------------------------------------------------------
// Priority chain
// ---------------------------------------------------------------------------

describe('deriveExpression — priority chain', () => {
  it('error beats everything else', () => {
    const frame = deriveExpression(
      inputs({
        chatStatus: 'error',
        hitlAwaiting: true,
        voiceState: 'speaking',
        reaction: 'joy',
        notificationPing: true,
        userTyping: true,
        inactivityStage: 3,
      })
    );
    expect(frame.expression).toBe('worried');
  });

  it('HITL awaiting beats voice, interaction and idle', () => {
    const frame = deriveExpression(
      inputs({
        hitlAwaiting: true,
        voiceState: 'speaking',
        chatStatus: 'streaming',
        reaction: 'joy',
      })
    );
    expect(frame.expression).toBe('question');
  });

  it('voice recording shows attentive (beats chat interaction)', () => {
    const frame = deriveExpression(
      inputs({ voiceState: 'recording', chatStatus: 'streaming', streamPhase: 'progress' })
    );
    expect(frame.expression).toBe('attentive');
  });

  it('voice processing shows thinking', () => {
    expect(deriveExpression(inputs({ voiceState: 'processing' })).expression).toBe('thinking');
  });

  it('voice speaking shows speaking', () => {
    expect(deriveExpression(inputs({ voiceState: 'speaking' })).expression).toBe('speaking');
  });

  it('voice listening (wake-word watch) does NOT override idle', () => {
    // 'listening' is the passive KWS state — eyes stay on the idle loop.
    expect(deriveExpression(inputs({ voiceState: 'listening' })).expression).toBe('neutral');
  });

  it('sending shows attentive with gaze toward the input (down)', () => {
    const frame = deriveExpression(inputs({ chatStatus: 'sending' }));
    expect(frame.expression).toBe('attentive');
    expect(frame.gaze).toEqual({ x: 0, y: 1 });
  });

  it('compacting shows focused', () => {
    expect(deriveExpression(inputs({ chatStatus: 'compacting' })).expression).toBe('focused');
  });

  it('streaming progress + tool step shows searching', () => {
    const frame = deriveExpression(
      inputs({ chatStatus: 'streaming', streamPhase: 'progress', lastStepKind: 'tool' })
    );
    expect(frame.expression).toBe('searching');
  });

  it('streaming progress + reasoning (or unknown) step shows thinking with gaze up', () => {
    const reasoning = deriveExpression(
      inputs({ chatStatus: 'streaming', streamPhase: 'progress', lastStepKind: 'reasoning' })
    );
    expect(reasoning.expression).toBe('thinking');
    expect(reasoning.gaze).toEqual({ x: -0.6, y: -1 });
    const unknown = deriveExpression(
      inputs({ chatStatus: 'streaming', streamPhase: 'progress', lastStepKind: null })
    );
    expect(unknown.expression).toBe('thinking');
  });

  it('streaming answer shows speaking', () => {
    const frame = deriveExpression(inputs({ chatStatus: 'streaming', streamPhase: 'answer' }));
    expect(frame.expression).toBe('speaking');
  });

  it('a held reaction wins over notification, typing and idle', () => {
    const frame = deriveExpression(
      inputs({ reaction: 'joy', notificationPing: true, userTyping: true, inactivityStage: 2 })
    );
    expect(frame.expression).toBe('joy');
  });

  it('a notification ping shows surprise with gaze toward the toast (top-right)', () => {
    const frame = deriveExpression(inputs({ notificationPing: true, userTyping: true }));
    expect(frame.expression).toBe('surprise');
    expect(frame.gaze).toEqual({ x: 1, y: -1 });
  });

  it('user typing shows attentive with gaze down toward the input', () => {
    const frame = deriveExpression(inputs({ userTyping: true, inactivityStage: 1 }));
    expect(frame.expression).toBe('attentive');
    expect(frame.gaze).toEqual({ x: 0, y: 1 });
  });

  it('inactivity stages: tired, then sleepy, then sleep', () => {
    expect(deriveExpression(inputs({ inactivityStage: 1 })).expression).toBe('tired');
    expect(deriveExpression(inputs({ inactivityStage: 2 })).expression).toBe('sleepy');
    expect(deriveExpression(inputs({ inactivityStage: 3 })).expression).toBe('sleep');
  });

  it('idle with psyche mood falls through to the mood mapping (soft poses only)', () => {
    expect(deriveExpression(inputs({ moodLabel: 'playful' })).expression).toBe('attentive');
    expect(deriveExpression(inputs({ moodLabel: 'reflective' })).expression).toBe('thinking');
    expect(deriveExpression(inputs({ moodLabel: 'melancholic' })).expression).toBe('neutral');
  });

  it('idle without psyche: night leans sleepy, morning is fresh-attentive, day neutral', () => {
    expect(deriveExpression(inputs({ hourOfDay: 23 })).expression).toBe('sleepy');
    expect(deriveExpression(inputs({ hourOfDay: 3 })).expression).toBe('sleepy');
    expect(deriveExpression(inputs({ hourOfDay: 7 })).expression).toBe('attentive');
    expect(deriveExpression(inputs({ hourOfDay: 14 })).expression).toBe('neutral');
  });

  it('a non-neutral mood wins over the hour bias; a neutral mood does not', () => {
    expect(deriveExpression(inputs({ moodLabel: 'energized', hourOfDay: 23 })).expression).toBe(
      'attentive'
    );
    expect(deriveExpression(inputs({ moodLabel: 'neutral', hourOfDay: 23 })).expression).toBe(
      'sleepy'
    );
  });
});

// ---------------------------------------------------------------------------
// Emotion → expression mapping (post-response reaction)
// ---------------------------------------------------------------------------

// ---------------------------------------------------------------------------
// Mood → idle expression mapping (all 14 canonical moods)
// ---------------------------------------------------------------------------

describe('moodToIdleExpression', () => {
  it.each([
    ['serene', 'neutral'],
    ['curious', 'attentive'],
    ['energized', 'attentive'],
    ['playful', 'attentive'],
    ['reflective', 'thinking'],
    ['agitated', 'neutral'],
    ['melancholic', 'neutral'],
    ['neutral', 'neutral'],
    ['content', 'neutral'],
    ['determined', 'neutral'],
    ['defiant', 'neutral'],
    ['resigned', 'neutral'],
    ['overwhelmed', 'neutral'],
    ['tender', 'neutral'],
  ] as const)('%s → %s', (mood, expected) => {
    expect(moodToIdleExpression(mood)).toBe(expected);
  });

  it('resting poses stay SOFT — the style silhouette is always readable', () => {
    // Owner arbitration 2026-08-21: a mood must never hold a squinted pose
    // at rest (that hid the selected eye style and read as unsettling).
    // Strong poses are per-turn accents; mood personality rides the gesture
    // family instead. Widening this set is a design decision, not a tweak.
    const SOFT_RESTING_POSES = new Set(['neutral', 'attentive', 'thinking']);
    const ALL_MOODS: MoodLabel[] = [
      'serene',
      'curious',
      'energized',
      'playful',
      'reflective',
      'agitated',
      'melancholic',
      'neutral',
      'content',
      'determined',
      'defiant',
      'resigned',
      'overwhelmed',
      'tender',
    ];
    for (const mood of ALL_MOODS) {
      expect(
        SOFT_RESTING_POSES.has(moodToIdleExpression(mood)),
        `mood '${mood}' rests on a strong pose`
      ).toBe(true);
    }
  });
});

describe('idleFamilyForMood', () => {
  it('maps each mood to its personality family (the mood channel at rest)', () => {
    expect(idleFamilyForMood('playful')).toBe('lively');
    expect(idleFamilyForMood('energized')).toBe('lively');
    expect(idleFamilyForMood('agitated')).toBe('lively');
    expect(idleFamilyForMood('serene')).toBe('calm');
    expect(idleFamilyForMood('content')).toBe('calm');
    expect(idleFamilyForMood('melancholic')).toBe('drowsy');
    expect(idleFamilyForMood('resigned')).toBe('drowsy');
    expect(idleFamilyForMood('overwhelmed')).toBe('drowsy');
  });

  it('resolveIdleFamily prefers the mood and falls back to the expression', () => {
    expect(resolveIdleFamily('playful', 'neutral')).toBe('lively');
    expect(resolveIdleFamily('overwhelmed', 'attentive')).toBe('drowsy');
    expect(resolveIdleFamily(null, 'attentive')).toBe('lively');
    expect(resolveIdleFamily(null, 'sleepy')).toBe('drowsy');
    expect(resolveIdleFamily(null, 'neutral')).toBe('calm');
  });
});

// ---------------------------------------------------------------------------
// Post-done reaction resolution — the FALLBACK path (ADR-253)
// ---------------------------------------------------------------------------

// ---------------------------------------------------------------------------
// Content heuristic — language-neutral (punctuation / emoji / structure only)
// ---------------------------------------------------------------------------

// ---------------------------------------------------------------------------
// Inactivity staging & hour bands
// ---------------------------------------------------------------------------

describe('inactivityStageFor', () => {
  it('maps elapsed idle time to progressive stages with exact boundaries', () => {
    expect(inactivityStageFor(0)).toBe(0);
    expect(inactivityStageFor(INACTIVITY_DROWSY_MS - 1)).toBe(0);
    expect(inactivityStageFor(INACTIVITY_DROWSY_MS)).toBe(1);
    expect(inactivityStageFor(INACTIVITY_SLEEPY_MS - 1)).toBe(1);
    expect(inactivityStageFor(INACTIVITY_SLEEPY_MS)).toBe(2);
    expect(inactivityStageFor(INACTIVITY_ASLEEP_MS - 1)).toBe(2);
    expect(inactivityStageFor(INACTIVITY_ASLEEP_MS)).toBe(3);
  });

  it('stages are ordered (drowsy < sleepy < asleep)', () => {
    expect(INACTIVITY_DROWSY_MS).toBeLessThan(INACTIVITY_SLEEPY_MS);
    expect(INACTIVITY_SLEEPY_MS).toBeLessThan(INACTIVITY_ASLEEP_MS);
  });
});

describe('hourBand', () => {
  it('classifies night, morning and day', () => {
    expect(hourBand(23)).toBe('night');
    expect(hourBand(0)).toBe('night');
    expect(hourBand(5)).toBe('night');
    expect(hourBand(6)).toBe('morning');
    expect(hourBand(9)).toBe('morning');
    expect(hourBand(10)).toBe('day');
    expect(hourBand(21)).toBe('day');
    expect(hourBand(22)).toBe('night');
  });
});

// ---------------------------------------------------------------------------
// Idle scheduling (RNG injected — deterministic)
// ---------------------------------------------------------------------------

describe('nextBlinkDelayMs / isDoubleBlink', () => {
  it('spans the configured range from the injected RNG', () => {
    expect(nextBlinkDelayMs(() => 0)).toBe(BLINK_MIN_DELAY_MS);
    expect(nextBlinkDelayMs(() => 1)).toBe(BLINK_MAX_DELAY_MS);
    const mid = nextBlinkDelayMs(() => 0.5);
    expect(mid).toBeGreaterThan(BLINK_MIN_DELAY_MS);
    expect(mid).toBeLessThan(BLINK_MAX_DELAY_MS);
  });

  it('double blinks are rare and RNG-driven', () => {
    expect(isDoubleBlink(() => 0.0)).toBe(true);
    expect(isDoubleBlink(() => 0.99)).toBe(false);
  });
});

// ---------------------------------------------------------------------------
// Idle life: random gesture library + gaze wander (all RNG-injected)
// ---------------------------------------------------------------------------

describe('idle gesture scheduling', () => {
  it('gesture delays span their configured random range', () => {
    expect(nextIdleGestureDelayMs(() => 0)).toBe(IDLE_GESTURE_MIN_DELAY_MS);
    expect(nextIdleGestureDelayMs(() => 1)).toBe(IDLE_GESTURE_MAX_DELAY_MS);
  });

  it('every idle-life expression maps to a mood family', () => {
    expect(idleFamilyFor('joy')).toBe('lively');
    expect(idleFamilyFor('excited')).toBe('lively');
    expect(idleFamilyFor('attentive')).toBe('lively');
    expect(idleFamilyFor('neutral')).toBe('calm');
    expect(idleFamilyFor('tender')).toBe('calm');
    expect(idleFamilyFor('bored')).toBe('calm');
    expect(idleFamilyFor('tired')).toBe('drowsy');
    expect(idleFamilyFor('sleepy')).toBe('drowsy');
  });

  it('gesture picks are personality-consistent: no bounce when drowsy, no slow blink when lively', () => {
    const seen = { lively: new Set<string>(), calm: new Set<string>(), drowsy: new Set<string>() };
    for (let r = 0; r < 1; r += 0.01) {
      seen.lively.add(pickIdleGesture(() => r, 'lively'));
      seen.calm.add(pickIdleGesture(() => r, 'calm'));
      seen.drowsy.add(pickIdleGesture(() => r, 'drowsy'));
    }
    expect(seen.lively.has('bounce')).toBe(true);
    expect(seen.lively.has('slow-blink')).toBe(false);
    expect(seen.calm.has('bounce')).toBe(false);
    expect(seen.drowsy.has('slow-blink')).toBe(true);
    expect(seen.drowsy.has('bounce')).toBe(false);
    expect(seen.drowsy.has('perk')).toBe(false);
    // Every family wanders its gaze (the dominant life signal).
    expect(seen.lively.has('saccade')).toBe(true);
    expect(seen.calm.has('saccade')).toBe(true);
    expect(seen.drowsy.has('saccade')).toBe(true);
  });

  it('rng extremes stay inside each weight table', () => {
    for (const family of ['lively', 'calm', 'drowsy'] as const) {
      expect(typeof pickIdleGesture(() => 0, family)).toBe('string');
      expect(typeof pickIdleGesture(() => 0.999, family)).toBe('string');
    }
  });

  it('saccade targets are small, glance targets are wide, both clamped', () => {
    const saccade = idleGazeTarget(() => 1, 'saccade');
    expect(Math.abs(saccade.x)).toBeLessThanOrEqual(0.35);
    expect(Math.abs(saccade.y)).toBeLessThanOrEqual(0.22);
    const glance = idleGazeTarget(() => 1, 'glance');
    expect(Math.abs(glance.x)).toBeGreaterThanOrEqual(0.5);
    expect(Math.abs(glance.x)).toBeLessThanOrEqual(0.85);
    // rng 0 is deterministic (pins the widget tests)
    expect(idleGazeTarget(() => 0, 'saccade')).toEqual({ x: -0.35, y: -0.22 });
  });

  it('mood flickers (mini idle scenes) belong to the awake families only', () => {
    const gesturesFor = (family: 'lively' | 'calm' | 'drowsy') => {
      const seen = new Set<string>();
      for (let r = 0; r < 1; r += 0.005) seen.add(pickIdleGesture(() => r, family));
      return seen;
    };
    expect(gesturesFor('lively').has('flicker')).toBe(true);
    expect(gesturesFor('calm').has('flicker')).toBe(true);
    expect(gesturesFor('drowsy').has('flicker')).toBe(false);
  });

  it('idle flickers are short scenes that always settle back to a free gaze', () => {
    expect(IDLE_FLICKERS.length).toBeGreaterThanOrEqual(3);
    for (const scene of IDLE_FLICKERS) {
      expect(scene.length).toBeGreaterThanOrEqual(2);
      const last = scene[scene.length - 1];
      expect(last.gaze).toBeNull();
      for (const step of scene) expect(step.ms).toBeGreaterThan(0);
    }
    // Deterministic pick for the widget tests.
    expect(pickIdleFlicker(() => 0)).toBe(IDLE_FLICKERS[0]);
    expect(pickIdleFlicker(() => 0.99)).toBe(IDLE_FLICKERS[IDLE_FLICKERS.length - 1]);
  });

  it('the asymmetric brow raise belongs to the awake families only', () => {
    const gesturesFor = (family: 'lively' | 'calm' | 'drowsy') => {
      const seen = new Set<string>();
      for (let r = 0; r < 1; r += 0.005) seen.add(pickIdleGesture(() => r, family));
      return seen;
    };
    expect(gesturesFor('lively').has('brow')).toBe(true);
    expect(gesturesFor('calm').has('brow')).toBe(true);
    expect(gesturesFor('drowsy').has('brow')).toBe(false);
  });

  it('silly beats are rare, RNG-gated, and picked from the whole silly set', () => {
    expect(isSillyTime(() => 0)).toBe(true);
    expect(isSillyTime(() => SILLY_PROBABILITY)).toBe(false);
    const seen = new Set<string>();
    for (let r = 0; r < 1; r += 0.01) seen.add(pickSillyGesture(() => r));
    expect(seen).toEqual(new Set(SILLY_GESTURES));
    expect(pickSillyGesture(() => 0)).toBe('swap');
    for (const silly of SILLY_GESTURES) {
      expect(GESTURE_DURATION_MS[silly]).toBeGreaterThan(800);
      expect(GESTURE_DURATION_MS[silly]).toBeLessThan(2500);
    }
  });

  it('emotes map the explicit expressions only', () => {
    expect(emoteForExpression('question')).toBe('?');
    expect(emoteForExpression('surprise')).toBe('!');
    expect(emoteForExpression('sleep')).toBe('z');
    expect(emoteForExpression('thinking')).toBe('…');
    expect(emoteForExpression('neutral')).toBeNull();
    expect(emoteForExpression('joy')).toBeNull();
    expect(emoteForExpression('speaking')).toBeNull();
  });

  it('a glance chains to the other side on the configured probability', () => {
    expect(shouldChainGlance(() => 0)).toBe(true);
    expect(shouldChainGlance(() => 0.99)).toBe(false);
  });

  it('the wake performance is a startle: jolt wide, check both sides, settle', () => {
    expect(WAKE_PERFORMANCE.length).toBeGreaterThanOrEqual(3);
    expect(WAKE_PERFORMANCE[0].expression).toBe('surprise');
    expect(WAKE_PERFORMANCE[WAKE_PERFORMANCE.length - 1].gaze).toBeNull();
    const xs = WAKE_PERFORMANCE.map(s => s.gaze?.x ?? 0);
    expect(Math.min(...xs)).toBeLessThan(0);
    expect(Math.max(...xs)).toBeGreaterThan(0);
    for (const step of WAKE_PERFORMANCE) expect(step.ms).toBeGreaterThan(0);
  });

  it('gaze hold times are RNG-driven within their ranges', () => {
    expect(gazeHoldMs(() => 0, 'saccade')).toBe(SACCADE_HOLD_MIN_MS);
    expect(gazeHoldMs(() => 1, 'glance')).toBe(GLANCE_HOLD_MAX_MS);
  });

  it('one-shot gestures carry a clearing duration covering their CSS animation', () => {
    for (const gesture of [
      'slow-blink',
      'half-blink',
      'squint',
      'tilt',
      'bounce',
      'perk',
      'brow',
    ] as const) {
      expect(GESTURE_DURATION_MS[gesture]).toBeGreaterThan(300);
      expect(GESTURE_DURATION_MS[gesture]).toBeLessThan(1500);
    }
  });
});

// ---------------------------------------------------------------------------
// Transition grammar & liveliness beats (2026-08-21 batch)
// ---------------------------------------------------------------------------

describe('transition grammar primitives', () => {
  it('pre-gaze blink triggers under its probability, not above', () => {
    expect(shouldBlinkBeforeGaze(() => PRE_GAZE_BLINK_PROBABILITY - 0.01)).toBe(true);
    expect(shouldBlinkBeforeGaze(() => PRE_GAZE_BLINK_PROBABILITY)).toBe(false);
    expect(shouldBlinkBeforeGaze(() => 0.99)).toBe(false);
  });

  it('the blink lead is shorter than the blink itself (the lid must cover the move)', () => {
    expect(PRE_GAZE_BLINK_LEAD_MS).toBeLessThan(BLINK_DURATION_MS);
  });

  it('urgent arrivals bypass the minimum hold; idle poses do not', () => {
    for (const urgent of ['worried', 'question', 'surprise', 'fear', 'wink'] as const) {
      expect(URGENT_ARRIVALS.has(urgent), urgent).toBe(true);
    }
    expect(URGENT_ARRIVALS.has('neutral')).toBe(false);
    expect(URGENT_ARRIVALS.has('joy')).toBe(false);
    expect(MIN_EXPRESSION_HOLD_MS).toBeGreaterThan(MASK_APPLY_DELAY_MS);
  });

  it('blink cadence follows the family: lively blinks sooner than drowsy', () => {
    expect(nextBlinkDelayMs(() => 0, 'lively')).toBeLessThan(nextBlinkDelayMs(() => 0, 'drowsy'));
    expect(nextBlinkDelayMs(() => 1, 'lively')).toBeLessThan(nextBlinkDelayMs(() => 1, 'drowsy'));
    // Default family is the calm reference band (compat call sites).
    expect(nextBlinkDelayMs(() => 0)).toBe(BLINK_MIN_DELAY_MS);
    expect(nextBlinkDelayMs(() => 1)).toBe(BLINK_MAX_DELAY_MS);
  });
});

describe('mood shift beats', () => {
  it('a cross-family rise plays the spark, a fall plays the settle', () => {
    expect(moodShiftPerformance('content', 'playful')).toBe(MOOD_SHIFT_RISE_PERFORMANCE);
    expect(moodShiftPerformance('resigned', 'serene')).toBe(MOOD_SHIFT_RISE_PERFORMANCE);
    expect(moodShiftPerformance('playful', 'melancholic')).toBe(MOOD_SHIFT_FALL_PERFORMANCE);
    expect(moodShiftPerformance('serene', 'overwhelmed')).toBe(MOOD_SHIFT_FALL_PERFORMANCE);
  });

  it('a same-family shift stays silent (the gesture cadence already moved)', () => {
    expect(moodShiftPerformance('content', 'serene')).toBeNull();
    expect(moodShiftPerformance('playful', 'energized')).toBeNull();
    expect(moodShiftPerformance('resigned', 'overwhelmed')).toBeNull();
  });

  it('both beats settle back to a free frame (last step gaze: null)', () => {
    for (const beat of [MOOD_SHIFT_RISE_PERFORMANCE, MOOD_SHIFT_FALL_PERFORMANCE]) {
      expect(beat[beat.length - 1].gaze).toBeNull();
    }
  });
});

describe('reading pattern', () => {
  it('walks the line left to right, slightly up, then carriage-returns', () => {
    const first = readingGazeAt(1);
    const second = readingGazeAt(2);
    const third = readingGazeAt(3);
    expect(second.gaze.x).toBeGreaterThan(first.gaze.x);
    expect(third.gaze.x).toBeGreaterThan(second.gaze.x);
    for (const step of [first, second, third]) {
      expect(step.gaze.y).toBeLessThan(0);
      expect(step.ms).toBe(READING_MOVE_MS);
    }
    // Step 0 (and every full cycle) is the quick carriage return to line start.
    expect(readingGazeAt(0).ms).toBe(READING_RETURN_MS);
    expect(readingGazeAt(4).gaze).toEqual(readingGazeAt(0).gaze);
  });
});

describe('proportional wake', () => {
  it('a short nap earns the quick recollection, deep sleep the full startle', () => {
    expect(wakePerformanceFor(0)).toBe(WAKE_SHORT_PERFORMANCE);
    expect(wakePerformanceFor(SHORT_NAP_MS - 1)).toBe(WAKE_SHORT_PERFORMANCE);
    expect(wakePerformanceFor(SHORT_NAP_MS)).toBe(WAKE_PERFORMANCE);
  });

  it('the short wake never startles (no surprise beat)', () => {
    expect(WAKE_SHORT_PERFORMANCE.some(s => s.expression === 'surprise')).toBe(false);
    expect(WAKE_PERFORMANCE[0].expression).toBe('surprise');
  });
});

describe('cartoon accessories', () => {
  const always: Rng = () => 0;
  const never: Rng = () => 0.999;

  it('only the emotions that earn one can summon one', () => {
    expect(accessoryForExpression('sad', always)).toBe('tear');
    expect(accessoryForExpression('worried', always)).toBe('sweat');
    expect(accessoryForExpression('fear', always)).toBe('sweat');
    expect(accessoryForExpression('joy', always)).toBe('sparkle');
    expect(accessoryForExpression('excited', always)).toBe('sparkle');
  });

  it('the rest of the vocabulary summons nothing at all', () => {
    const summoning = EYE_EXPRESSIONS.filter(
      expression => accessoryForExpression(expression, always) !== null
    );
    expect(summoning.sort()).toEqual(['excited', 'fear', 'joy', 'sad', 'worried']);
  });

  it('stays RARE — an unlucky roll brings nothing, whatever the emotion', () => {
    EYE_EXPRESSIONS.forEach(expression => {
      expect(accessoryForExpression(expression, never)).toBeNull();
    });
  });

  it('never fires more often than one arrival in three', () => {
    // Rarity is the whole design: an accessory on every sad face stops
    // meaning "this one really landed" within a day of use.
    const rates = EYE_EXPRESSIONS.map(expression => {
      let hits = 0;
      for (let index = 0; index < 1000; index += 1) {
        if (accessoryForExpression(expression, () => index / 1000)) hits += 1;
      }
      return hits / 1000;
    });
    expect(Math.max(...rates)).toBeLessThanOrEqual(0.35);
  });

  it('declares a duration for every accessory it can produce', () => {
    (['tear', 'sweat', 'sparkle'] as const).forEach(accessory => {
      expect(ACCESSORY_DURATION_MS[accessory]).toBeGreaterThan(0);
    });
  });
});
