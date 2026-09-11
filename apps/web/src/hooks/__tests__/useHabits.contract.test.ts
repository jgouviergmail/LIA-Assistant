/**
 * The habit-intent vocabulary is declared once per layer and pinned across
 * them: the backend's `IMMEDIATE_INTENTS` is pinned to the locale keys by
 * `test_recurrence_ledger.py`; this pins the frontend constant to the same
 * keys, so a value one layer knows and the other cannot name is caught here
 * rather than rendered as an empty slot.
 */
import { describe, expect, it } from 'vitest';

import { HABIT_INTENTS, habitIntentOf } from '@/hooks/useHabits';
import en from '../../../locales/en/translation.json';

describe('habit intents', () => {
  it('match the settings.habits.intent locale keys exactly', () => {
    const labels = (en as { settings: { habits: { intent: Record<string, string> } } }).settings
      .habits.intent;
    expect([...HABIT_INTENTS].sort()).toEqual(Object.keys(labels).sort());
  });

  it('narrow a payload value to the vocabulary, or to nothing', () => {
    expect(habitIntentOf('search')).toBe('search');
    expect(habitIntentOf('frobnicate')).toBeNull();
    expect(habitIntentOf(42)).toBeNull();
    expect(habitIntentOf(undefined)).toBeNull();
  });
});
