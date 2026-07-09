/**
 * psycheStore — live psyche state transitions and selectors.
 *
 * Covers both feed paths (SSE done metadata + full server state), the
 * non-mutation guarantee on React Query cached data (BUG-4 regression) and
 * the reset/preference setters.
 */

import { describe, it, expect, beforeEach, vi, afterEach } from 'vitest';

import { usePsycheStore } from '@/stores/psycheStore';
import type { PsycheState, PsycheStateSummary } from '@/types/psyche';

const SSE_SUMMARY: PsycheStateSummary = {
  mood_label: 'playful',
  mood_color: '#22c55e',
  mood_pleasure: 0.8,
  mood_arousal: 0.4,
  mood_dominance: 0.6,
  active_emotion: 'joy',
  emotion_intensity: 0.9,
  relationship_stage: 'EXPLORATORY',
};

function makeFullState(overrides: Partial<PsycheState> = {}): PsycheState {
  return {
    mood_label: 'serene',
    mood_color: '#38bdf8',
    mood_pleasure: 0.5,
    mood_arousal: 0.2,
    mood_dominance: 0.4,
    active_emotions: [
      { name: 'calm', intensity: 0.3 },
      { name: 'curiosity', intensity: 0.7 },
      { name: 'gratitude', intensity: 0.5 },
    ],
    relationship_stage: 'STABLE',
    updated_at: '2026-07-01T10:00:00Z',
    ...overrides,
  } as PsycheState;
}

beforeEach(() => {
  usePsycheStore.getState().reset();
});

afterEach(() => {
  vi.useRealTimers();
});

describe('psycheStore — initial state', () => {
  it('starts neutral, avatar displayed, engine disabled', () => {
    const s = usePsycheStore.getState();

    expect(s.moodLabel).toBe('neutral');
    expect(s.moodColor).toBe('#9ca3af');
    expect(s.activeEmotion).toBeNull();
    expect(s.emotionIntensity).toBe(0);
    expect(s.relationshipStage).toBe('ORIENTATION');
    expect(s.lastUpdated).toBeNull();
    expect(s.fullState).toBeNull();
    expect(s.displayAvatar).toBe(true);
    expect(s.enabled).toBe(false);
  });
});

describe('psycheStore — updateFromSSE', () => {
  it('maps every summary field and stamps lastUpdated', () => {
    vi.useFakeTimers();
    vi.setSystemTime(new Date('2026-07-09T12:00:00Z'));

    usePsycheStore.getState().updateFromSSE(SSE_SUMMARY);

    const s = usePsycheStore.getState();
    expect(s.moodLabel).toBe('playful');
    expect(s.moodColor).toBe('#22c55e');
    expect(s.moodPleasure).toBe(0.8);
    expect(s.moodArousal).toBe(0.4);
    expect(s.moodDominance).toBe(0.6);
    expect(s.activeEmotion).toBe('joy');
    expect(s.emotionIntensity).toBe(0.9);
    expect(s.relationshipStage).toBe('EXPLORATORY');
    expect(s.lastUpdated).toBe('2026-07-09T12:00:00.000Z');
  });

  it('does not touch the full server snapshot', () => {
    const full = makeFullState();
    usePsycheStore.getState().updateFromFullState(full);

    usePsycheStore.getState().updateFromSSE(SSE_SUMMARY);

    expect(usePsycheStore.getState().fullState).toBe(full);
  });
});

describe('psycheStore — updateFromFullState', () => {
  it('derives the top emotion by intensity and stores the snapshot', () => {
    const full = makeFullState();

    usePsycheStore.getState().updateFromFullState(full);

    const s = usePsycheStore.getState();
    expect(s.moodLabel).toBe('serene');
    expect(s.activeEmotion).toBe('curiosity'); // highest intensity (0.7)
    expect(s.emotionIntensity).toBe(0.7);
    expect(s.relationshipStage).toBe('STABLE');
    expect(s.lastUpdated).toBe('2026-07-01T10:00:00Z');
    expect(s.fullState).toBe(full);
  });

  it('sorts a COPY — the React Query cached array is not mutated (BUG-4)', () => {
    const emotions = [
      { name: 'calm', intensity: 0.3 },
      { name: 'curiosity', intensity: 0.7 },
    ];
    const full = makeFullState({ active_emotions: emotions as PsycheState['active_emotions'] });

    usePsycheStore.getState().updateFromFullState(full);

    expect(emotions.map(e => e.name)).toEqual(['calm', 'curiosity']);
  });

  it('falls back to no active emotion when the list is empty', () => {
    usePsycheStore.getState().updateFromFullState(makeFullState({ active_emotions: [] }));

    const s = usePsycheStore.getState();
    expect(s.activeEmotion).toBeNull();
    expect(s.emotionIntensity).toBe(0);
  });
});

describe('psycheStore — setters and reset', () => {
  it('setDisplayAvatar and setEnabled update the preferences', () => {
    usePsycheStore.getState().setDisplayAvatar(false);
    usePsycheStore.getState().setEnabled(true);

    expect(usePsycheStore.getState().displayAvatar).toBe(false);
    expect(usePsycheStore.getState().enabled).toBe(true);
  });

  it('reset restores the pristine state', () => {
    usePsycheStore.getState().updateFromSSE(SSE_SUMMARY);
    usePsycheStore.getState().updateFromFullState(makeFullState());
    usePsycheStore.getState().setEnabled(true);

    usePsycheStore.getState().reset();

    const s = usePsycheStore.getState();
    expect(s.moodLabel).toBe('neutral');
    expect(s.fullState).toBeNull();
    expect(s.enabled).toBe(false);
    expect(s.lastUpdated).toBeNull();
  });
});
