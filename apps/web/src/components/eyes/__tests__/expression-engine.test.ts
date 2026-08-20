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

import {
  deriveExpression,
  deriveReaction,
  contentHeuristicExpression,
  emotionToExpression,
  moodToIdleExpression,
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

  it('idle with psyche mood falls through to the mood mapping', () => {
    expect(deriveExpression(inputs({ moodLabel: 'playful' })).expression).toBe('joy');
    expect(deriveExpression(inputs({ moodLabel: 'melancholic' })).expression).toBe('sad');
  });

  it('idle without psyche: night leans sleepy, morning is fresh-attentive, day neutral', () => {
    expect(deriveExpression(inputs({ hourOfDay: 23 })).expression).toBe('sleepy');
    expect(deriveExpression(inputs({ hourOfDay: 3 })).expression).toBe('sleepy');
    expect(deriveExpression(inputs({ hourOfDay: 7 })).expression).toBe('attentive');
    expect(deriveExpression(inputs({ hourOfDay: 14 })).expression).toBe('neutral');
  });

  it('a non-neutral mood wins over the hour bias; a neutral mood does not', () => {
    expect(deriveExpression(inputs({ moodLabel: 'energized', hourOfDay: 23 })).expression).toBe(
      'excited'
    );
    expect(deriveExpression(inputs({ moodLabel: 'neutral', hourOfDay: 23 })).expression).toBe(
      'sleepy'
    );
  });
});

// ---------------------------------------------------------------------------
// Emotion → expression mapping (post-response reaction)
// ---------------------------------------------------------------------------

describe('emotionToExpression', () => {
  it.each([
    ['joy', 'joy'],
    ['gratitude', 'tender'],
    ['pride', 'joy'],
    ['amusement', 'joy'],
    ['enthusiasm', 'excited'],
    ['tenderness', 'tender'],
    ['playfulness', 'joy'],
    ['relief', 'joy'],
    ['wonder', 'surprise'],
    ['frustration', 'anger'],
    ['concern', 'worried'],
    ['melancholy', 'sad'],
    ['disappointment', 'sad'],
    ['nervousness', 'fear'],
    ['curiosity', 'attentive'],
    ['serenity', 'neutral'],
    ['surprise', 'surprise'],
    ['empathy', 'tender'],
    ['confusion', 'question'],
    ['determination', 'focused'],
    ['protectiveness', 'focused'],
    ['resolve', 'focused'],
  ] as const)('%s → %s', (emotion, expected) => {
    expect(emotionToExpression(emotion)).toBe(expected);
  });

  it('unknown emotion falls back to neutral', () => {
    expect(emotionToExpression('unheard_of')).toBe('neutral');
  });
});

// ---------------------------------------------------------------------------
// Mood → idle expression mapping (all 14 canonical moods)
// ---------------------------------------------------------------------------

describe('moodToIdleExpression', () => {
  it.each([
    ['serene', 'neutral'],
    ['curious', 'attentive'],
    ['energized', 'excited'],
    ['playful', 'joy'],
    ['reflective', 'thinking'],
    ['agitated', 'worried'],
    ['melancholic', 'sad'],
    ['neutral', 'neutral'],
    ['content', 'joy'],
    ['determined', 'focused'],
    ['defiant', 'focused'],
    ['resigned', 'bored'],
    ['overwhelmed', 'tired'],
    ['tender', 'tender'],
  ] as const)('%s → %s', (mood, expected) => {
    expect(moodToIdleExpression(mood)).toBe(expected);
  });
});

// ---------------------------------------------------------------------------
// Post-done reaction resolution (self-report first, heuristic fallback)
// ---------------------------------------------------------------------------

describe('deriveReaction', () => {
  it('uses the per-turn psyche self-report when present', () => {
    expect(
      deriveReaction({
        psycheEmotions: [{ name: 'enthusiasm', intensity: 0.7 }],
        content: 'Voilà !',
        isError: false,
        hasArtifacts: false,
      })
    ).toBe('excited');
  });

  it('ignores a below-threshold emotion and falls back to the heuristic', () => {
    expect(
      deriveReaction({
        psycheEmotions: [{ name: 'frustration', intensity: 0.1 }],
        content: 'Et voilà le résultat ! Superbe !',
        isError: false,
        hasArtifacts: false,
      })
    ).toBe('excited');
  });

  it('falls back to the content heuristic when psyche is absent (race or disabled)', () => {
    expect(
      deriveReaction({
        psycheEmotions: null,
        content: 'Would you like me to go further?',
        isError: false,
        hasArtifacts: false,
      })
    ).toBe('question');
  });

  it('returns null when neither source yields a signal', () => {
    expect(
      deriveReaction({
        psycheEmotions: null,
        content: 'Voici la liste des tâches du jour.',
        isError: false,
        hasArtifacts: false,
      })
    ).toBeNull();
  });
});

// ---------------------------------------------------------------------------
// Content heuristic — language-neutral (punctuation / emoji / structure only)
// ---------------------------------------------------------------------------

describe('contentHeuristicExpression', () => {
  it('error responses look worried', () => {
    expect(
      contentHeuristicExpression({ content: 'anything', isError: true, hasArtifacts: false })
    ).toBe('worried');
  });

  it('generated artifacts (images/documents) look joyful — proud to show', () => {
    expect(
      contentHeuristicExpression({ content: 'Voici :', isError: false, hasArtifacts: true })
    ).toBe('joy');
  });

  it('joyful emoji → joy (any language)', () => {
    expect(
      contentHeuristicExpression({ content: '任务完成 🎉', isError: false, hasArtifacts: false })
    ).toBe('joy');
    expect(
      contentHeuristicExpression({ content: 'Fatto! 😄', isError: false, hasArtifacts: false })
    ).toBe('joy');
  });

  it('sad emoji → sad', () => {
    expect(
      contentHeuristicExpression({ content: 'Désolée… 😢', isError: false, hasArtifacts: false })
    ).toBe('sad');
  });

  it('trailing question mark → question, including fullwidth (zh)', () => {
    expect(
      contentHeuristicExpression({
        content: 'Souhaitez-vous continuer ?',
        isError: false,
        hasArtifacts: false,
      })
    ).toBe('question');
    expect(
      contentHeuristicExpression({ content: '需要我继续吗？', isError: false, hasArtifacts: false })
    ).toBe('question');
    expect(
      contentHeuristicExpression({
        content: 'Weiter machen?\n',
        isError: false,
        hasArtifacts: false,
      })
    ).toBe('question');
  });

  it('a trailing question mark inside a code fence does not count', () => {
    expect(
      contentHeuristicExpression({
        content: 'Voici :\n```py\nx?\n```',
        isError: false,
        hasArtifacts: false,
      })
    ).toBe('focused');
  });

  it('two or more exclamation marks → excited, including fullwidth (zh)', () => {
    expect(
      contentHeuristicExpression({
        content: 'Bravo ! C’est fait !',
        isError: false,
        hasArtifacts: false,
      })
    ).toBe('excited');
    expect(
      contentHeuristicExpression({
        content: '太棒了！完成了！',
        isError: false,
        hasArtifacts: false,
      })
    ).toBe('excited');
  });

  it('a single exclamation mark is not enough', () => {
    expect(
      contentHeuristicExpression({ content: 'Voilà !', isError: false, hasArtifacts: false })
    ).toBeNull();
  });

  it('a fenced code block → focused', () => {
    expect(
      contentHeuristicExpression({
        content: 'Voici le script :\n```bash\nls\n```',
        isError: false,
        hasArtifacts: false,
      })
    ).toBe('focused');
  });

  it('plain informative text yields no reaction', () => {
    expect(
      contentHeuristicExpression({
        content: 'Votre réunion est à 15h.',
        isError: false,
        hasArtifacts: false,
      })
    ).toBeNull();
    expect(
      contentHeuristicExpression({ content: '', isError: false, hasArtifacts: false })
    ).toBeNull();
  });

  it('priority: emoji beats trailing question mark', () => {
    expect(
      contentHeuristicExpression({ content: 'On y va ? 🎉', isError: false, hasArtifacts: false })
    ).toBe('joy');
  });
});

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
      seen.lively.add(pickIdleGesture(() => r, 'joy'));
      seen.calm.add(pickIdleGesture(() => r, 'neutral'));
      seen.drowsy.add(pickIdleGesture(() => r, 'sleepy'));
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
    for (const expression of ['joy', 'neutral', 'sleepy'] as const) {
      expect(typeof pickIdleGesture(() => 0, expression)).toBe('string');
      expect(typeof pickIdleGesture(() => 0.999, expression)).toBe('string');
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
    const gesturesFor = (expression: 'joy' | 'neutral' | 'sleepy') => {
      const seen = new Set<string>();
      for (let r = 0; r < 1; r += 0.005) seen.add(pickIdleGesture(() => r, expression));
      return seen;
    };
    expect(gesturesFor('joy').has('flicker')).toBe(true);
    expect(gesturesFor('neutral').has('flicker')).toBe(true);
    expect(gesturesFor('sleepy').has('flicker')).toBe(false);
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
    const gesturesFor = (expression: 'joy' | 'neutral' | 'sleepy') => {
      const seen = new Set<string>();
      for (let r = 0; r < 1; r += 0.005) seen.add(pickIdleGesture(() => r, expression));
      return seen;
    };
    expect(gesturesFor('joy').has('brow')).toBe(true);
    expect(gesturesFor('neutral').has('brow')).toBe(true);
    expect(gesturesFor('sleepy').has('brow')).toBe(false);
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
