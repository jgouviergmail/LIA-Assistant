/**
 * Eyes widget stores — ephemeral live signals + persisted display preferences.
 *
 * `eyesSignalsStore` carries the per-turn signals (execution-step kind,
 * notification ping, typing activity, post-response reaction) that non-React
 * code (SSE handlers, page callbacks) records for the widget to read.
 * `eyesWidgetStore` persists visibility/size/position across reloads
 * (localStorage, non-sensitive display preferences).
 */

import { describe, it, expect, beforeEach } from 'vitest';

import { useEyesSignalsStore, NOTIFICATION_SIGNAL_TTL_MS } from '@/stores/eyesSignalsStore';
import { useEyesWidgetStore, EYES_SIZES } from '@/stores/eyesWidgetStore';
import { EYES_WIDGET_PREFS_KEY } from '@/lib/constants';
import { REACTION_HOLD_MS, TYPING_ACTIVE_MS } from '@/components/eyes/expression-engine';

// ---------------------------------------------------------------------------
// eyesSignalsStore
// ---------------------------------------------------------------------------

describe('eyesSignalsStore', () => {
  beforeEach(() => {
    useEyesSignalsStore.getState().reset();
  });

  it('records the latest execution-step kind', () => {
    useEyesSignalsStore.getState().recordStep('tool');
    expect(useEyesSignalsStore.getState().lastStepKind).toBe('tool');
    useEyesSignalsStore.getState().recordStep('reasoning');
    expect(useEyesSignalsStore.getState().lastStepKind).toBe('reasoning');
  });

  it('a new turn clears the step kind and any held reaction', () => {
    useEyesSignalsStore.getState().recordStep('tool');
    useEyesSignalsStore.getState().setReaction('joy', 1000);
    useEyesSignalsStore.getState().beginTurn();
    expect(useEyesSignalsStore.getState().lastStepKind).toBeNull();
    expect(useEyesSignalsStore.getState().reaction).toBeNull();
  });

  it('notification ping is live within its TTL and expires after', () => {
    const s = useEyesSignalsStore.getState();
    expect(s.isNotificationLive(5000)).toBe(false);
    s.recordNotification(5000);
    expect(useEyesSignalsStore.getState().isNotificationLive(5000)).toBe(true);
    expect(
      useEyesSignalsStore.getState().isNotificationLive(5000 + NOTIFICATION_SIGNAL_TTL_MS - 1)
    ).toBe(true);
    expect(
      useEyesSignalsStore.getState().isNotificationLive(5000 + NOTIFICATION_SIGNAL_TTL_MS)
    ).toBe(false);
  });

  it('typing activity is live within its window and expires after', () => {
    useEyesSignalsStore.getState().recordTyping(2000);
    expect(useEyesSignalsStore.getState().isTypingLive(2000 + TYPING_ACTIVE_MS - 1)).toBe(true);
    expect(useEyesSignalsStore.getState().isTypingLive(2000 + TYPING_ACTIVE_MS)).toBe(false);
  });

  it('a reaction is held for its window then reads as expired', () => {
    useEyesSignalsStore.getState().setReaction('excited', 1, 'none', 1000);
    expect(useEyesSignalsStore.getState().liveReaction(1000 + REACTION_HOLD_MS - 1)).toBe(
      'excited'
    );
    expect(useEyesSignalsStore.getState().liveReaction(1000 + REACTION_HOLD_MS)).toBeNull();
  });

  it('setReaction(null) clears the held reaction', () => {
    useEyesSignalsStore.getState().setReaction('joy', 1, 'none', 1000);
    useEyesSignalsStore.getState().setReaction(null, 1, 'none', 2000);
    expect(useEyesSignalsStore.getState().liveReaction(2000)).toBeNull();
  });

  it('carries how forcefully the answer was written, for the same window', () => {
    useEyesSignalsStore.getState().setReaction('joy', 1.3, 'none', 1000);
    expect(useEyesSignalsStore.getState().liveEmphasis(1000 + REACTION_HOLD_MS - 1)).toBe(1.3);
    // Once the reaction is over the face goes back to its authored amplitude —
    // an emphasis that outlived its answer would colour unrelated expressions.
    expect(useEyesSignalsStore.getState().liveEmphasis(1000 + REACTION_HOLD_MS)).toBe(1);
  });

  it('reads as unemphatic when there is no reaction at all', () => {
    expect(useEyesSignalsStore.getState().liveEmphasis(5000)).toBe(1);
  });

  it('defaults the emphasis when a caller omits it', () => {
    useEyesSignalsStore.getState().setReaction('sad', undefined, 'none', 1000);
    expect(useEyesSignalsStore.getState().liveEmphasis(1000)).toBe(1);
  });

  it('reset returns every signal to its initial value', () => {
    const s = useEyesSignalsStore.getState();
    s.recordStep('tool');
    s.recordNotification(1);
    s.recordTyping(1);
    s.setReaction('joy', 1);
    s.reset();
    const after = useEyesSignalsStore.getState();
    expect(after.lastStepKind).toBeNull();
    expect(after.isNotificationLive(2)).toBe(false);
    expect(after.isTypingLive(2)).toBe(false);
    expect(after.liveReaction(2)).toBeNull();
  });
});

// ---------------------------------------------------------------------------
// eyesWidgetStore (persisted preferences)
// ---------------------------------------------------------------------------

describe('eyesWidgetStore', () => {
  beforeEach(() => {
    localStorage.removeItem(EYES_WIDGET_PREFS_KEY);
    useEyesWidgetStore.getState().reset();
  });

  it('defaults: visible, responsive auto size, no custom position', () => {
    const s = useEyesWidgetStore.getState();
    expect(s.visible).toBe(true);
    expect(s.size).toBe('auto');
    expect(s.position).toBeNull();
  });

  it('setVisible toggles and persists', () => {
    useEyesWidgetStore.getState().setVisible(false);
    expect(useEyesWidgetStore.getState().visible).toBe(false);
    const raw = localStorage.getItem(EYES_WIDGET_PREFS_KEY);
    expect(raw).toContain('"visible":false');
  });

  it('cycleSize leaves auto onto md, then walks md → lg → sm → md', () => {
    useEyesWidgetStore.getState().cycleSize();
    expect(useEyesWidgetStore.getState().size).toBe('md');
    useEyesWidgetStore.getState().cycleSize();
    expect(useEyesWidgetStore.getState().size).toBe('lg');
    useEyesWidgetStore.getState().cycleSize();
    expect(useEyesWidgetStore.getState().size).toBe('sm');
    useEyesWidgetStore.getState().cycleSize();
    expect(useEyesWidgetStore.getState().size).toBe('md');
  });

  it('EYES_SIZES exposes the three ordered presets', () => {
    expect(EYES_SIZES).toEqual(['sm', 'md', 'lg']);
  });

  it('setPosition stores viewport percentages clamped to [0, 100]', () => {
    useEyesWidgetStore.getState().setPosition({ xPct: 120, yPct: -4 });
    expect(useEyesWidgetStore.getState().position).toEqual({ xPct: 100, yPct: 0 });
    useEyesWidgetStore.getState().setPosition({ xPct: 33.3, yPct: 66.6 });
    expect(useEyesWidgetStore.getState().position).toEqual({ xPct: 33.3, yPct: 66.6 });
  });

  it('keeps a position PER SURFACE — the landing spot never becomes the chat spot', () => {
    // The chat clamps its widget off the Delete button through its dock; the
    // landing has no dock, and its visitor may have no account. A spot
    // dragged on one must not move the other.
    useEyesWidgetStore.getState().setLandingPosition({ xPct: 80, yPct: 90 });
    expect(useEyesWidgetStore.getState().landingPosition).toEqual({ xPct: 80, yPct: 90 });
    expect(useEyesWidgetStore.getState().position).toBeNull();
    useEyesWidgetStore.getState().setPosition({ xPct: 10, yPct: 20 });
    expect(useEyesWidgetStore.getState().landingPosition).toEqual({ xPct: 80, yPct: 90 });
    expect(useEyesWidgetStore.getState().position).toEqual({ xPct: 10, yPct: 20 });
  });

  it('clamps the landing position to the viewport and persists it', () => {
    useEyesWidgetStore.getState().setLandingPosition({ xPct: 140, yPct: -5 });
    expect(useEyesWidgetStore.getState().landingPosition).toEqual({ xPct: 100, yPct: 0 });
    const persisted = JSON.parse(localStorage.getItem(EYES_WIDGET_PREFS_KEY) ?? '{}');
    expect(persisted.state.landingPosition).toEqual({ xPct: 100, yPct: 0 });
  });

  it('reset restores defaults (including position)', () => {
    const s = useEyesWidgetStore.getState();
    s.setVisible(false);
    s.setSize('lg');
    s.setPosition({ xPct: 10, yPct: 10 });
    s.setLandingPosition({ xPct: 90, yPct: 90 });
    useEyesWidgetStore.getState().reset();
    const after = useEyesWidgetStore.getState();
    expect(after.visible).toBe(true);
    expect(after.size).toBe('auto');
    expect(after.position).toBeNull();
    expect(after.landingPosition).toBeNull();
  });

  it('setStyle applies a registry style and ignores an unknown one', () => {
    useEyesWidgetStore.getState().setStyle('billes');
    expect(useEyesWidgetStore.getState().style).toBe('billes');
    // A stale/foreign id (e.g. from a downgraded build) must be a no-op.
    useEyesWidgetStore.getState().setStyle('vintage' as never);
    expect(useEyesWidgetStore.getState().style).toBe('billes');
  });

  it('rehydrating a persisted style keeps it when the registry still has it', async () => {
    localStorage.setItem(
      EYES_WIDGET_PREFS_KEY,
      JSON.stringify({ state: { visible: true, size: 'md', style: 'anneaux', position: null } })
    );
    await useEyesWidgetStore.persist.rehydrate();
    expect(useEyesWidgetStore.getState().style).toBe('anneaux');
    expect(useEyesWidgetStore.getState().size).toBe('md');
  });

  it('rehydrating a stale persisted style falls back to the default', async () => {
    localStorage.setItem(
      EYES_WIDGET_PREFS_KEY,
      JSON.stringify({
        state: { visible: true, size: 'md', style: 'retired-style', position: null },
      })
    );
    await useEyesWidgetStore.persist.rehydrate();
    expect(useEyesWidgetStore.getState().style).toBe('cozmo');
  });

  it('rehydrating with nothing persisted keeps the defaults (merge undefined branch)', async () => {
    localStorage.removeItem(EYES_WIDGET_PREFS_KEY);
    await useEyesWidgetStore.persist.rehydrate();
    expect(useEyesWidgetStore.getState().style).toBe('cozmo');
    expect(useEyesWidgetStore.getState().size).toBe('auto');
  });
});

describe('eyesSignalsStore — the answer register (ADR-253)', () => {
  beforeEach(() => {
    useEyesSignalsStore.getState().reset();
  });

  it('carries the one-shot accent for the same window as its reaction', () => {
    useEyesSignalsStore.getState().setReaction('excited', 1.5, 'sparkle', 1000);
    expect(useEyesSignalsStore.getState().liveAccent(1000 + REACTION_HOLD_MS - 1)).toBe('sparkle');
    // Once the reaction is over the accent is over with it: a beat that
    // outlived its answer would punctuate an unrelated expression.
    expect(useEyesSignalsStore.getState().liveAccent(1000 + REACTION_HOLD_MS)).toBe('none');
  });

  it('reads as unaccented when there is no reaction at all', () => {
    expect(useEyesSignalsStore.getState().liveAccent(5000)).toBe('none');
  });

  it('defaults the accent when a caller omits it', () => {
    useEyesSignalsStore.getState().setReaction('joy', 1, undefined, 1000);
    expect(useEyesSignalsStore.getState().liveAccent(1000)).toBe('none');
  });

  it('holds the declared tone until the turn that consumes it', () => {
    const tone = { register: 'warm', intensity: 0.6, accent: 'nod' } as const;
    useEyesSignalsStore.getState().setTone(tone);
    expect(useEyesSignalsStore.getState().pendingTone).toEqual(tone);
    // A new turn must not inherit the previous answer's register.
    useEyesSignalsStore.getState().beginTurn();
    expect(useEyesSignalsStore.getState().pendingTone).toBeNull();
  });

  it('clears the tone when a done event carries none', () => {
    useEyesSignalsStore.getState().setTone({ register: 'weary', intensity: 0.4, accent: 'sigh' });
    useEyesSignalsStore.getState().setTone(null);
    expect(useEyesSignalsStore.getState().pendingTone).toBeNull();
  });
});
