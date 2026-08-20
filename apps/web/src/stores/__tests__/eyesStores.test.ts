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
    useEyesSignalsStore.getState().setReaction('excited', 1000);
    expect(useEyesSignalsStore.getState().liveReaction(1000 + REACTION_HOLD_MS - 1)).toBe(
      'excited'
    );
    expect(useEyesSignalsStore.getState().liveReaction(1000 + REACTION_HOLD_MS)).toBeNull();
  });

  it('setReaction(null) clears the held reaction', () => {
    useEyesSignalsStore.getState().setReaction('joy', 1000);
    useEyesSignalsStore.getState().setReaction(null, 2000);
    expect(useEyesSignalsStore.getState().liveReaction(2000)).toBeNull();
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

  it('reset restores defaults (including position)', () => {
    const s = useEyesWidgetStore.getState();
    s.setVisible(false);
    s.setSize('lg');
    s.setPosition({ xPct: 10, yPct: 10 });
    useEyesWidgetStore.getState().reset();
    const after = useEyesWidgetStore.getState();
    expect(after.visible).toBe(true);
    expect(after.size).toBe('auto');
    expect(after.position).toBeNull();
  });
});
