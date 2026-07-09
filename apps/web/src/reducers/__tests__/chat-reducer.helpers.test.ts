/**
 * chat-reducer — sessionStorage-backed helpers.
 *
 * Covers createInitialState hydration (valid, invalid JSON, non-array,
 * truncation) and persistDebugMetricsHistory (trim + quota errors swallowed).
 * The SSR branches (`typeof window === 'undefined'`) live in
 * chat-reducer.helpers.node.test.ts (node environment).
 */

import { describe, it, expect, beforeEach, vi, afterEach } from 'vitest';

import { createInitialState, persistDebugMetricsHistory } from '@/reducers/chat-reducer';
import { initialChatState, type DebugMetricsEntry } from '@/types/chat-state';
import type { DebugMetrics } from '@/types/chat';

const STORAGE_KEY = 'lia_debug_metrics_history';

function makeEntry(id: string): DebugMetricsEntry {
  return {
    id,
    timestamp: new Date('2026-01-01T00:00:00Z'),
    query: `q-${id}`,
    metrics: {} as DebugMetrics,
  };
}

beforeEach(() => {
  sessionStorage.clear();
});

afterEach(() => {
  vi.restoreAllMocks();
});

describe('createInitialState', () => {
  it('returns the pristine initial state when nothing is stored', () => {
    const state = createInitialState();

    expect(state).toEqual(initialChatState);
  });

  it('hydrates debugMetricsHistory from sessionStorage', () => {
    const entries = [makeEntry('e-1'), makeEntry('e-2')];
    sessionStorage.setItem(STORAGE_KEY, JSON.stringify(entries));

    const state = createInitialState();

    expect(state.debugMetricsHistory).toHaveLength(2);
    expect(state.debugMetricsHistory.map(e => e.id)).toEqual(['e-1', 'e-2']);
  });

  it('keeps only the 50 most recent stored entries', () => {
    const entries = Array.from({ length: 60 }, (_, i) => makeEntry(`e-${i}`));
    sessionStorage.setItem(STORAGE_KEY, JSON.stringify(entries));

    const state = createInitialState();

    expect(state.debugMetricsHistory).toHaveLength(50);
    // slice(-50): the OLDEST 10 are dropped.
    expect(state.debugMetricsHistory[0].id).toBe('e-10');
    expect(state.debugMetricsHistory[49].id).toBe('e-59');
  });

  it('starts fresh on invalid JSON', () => {
    sessionStorage.setItem(STORAGE_KEY, '{not json');

    const state = createInitialState();

    expect(state.debugMetricsHistory).toEqual([]);
  });

  it('starts fresh when the stored value is not an array', () => {
    sessionStorage.setItem(STORAGE_KEY, JSON.stringify({ sneaky: 'object' }));

    const state = createInitialState();

    expect(state.debugMetricsHistory).toEqual([]);
  });
});

describe('persistDebugMetricsHistory', () => {
  it('persists the history to sessionStorage', () => {
    persistDebugMetricsHistory([makeEntry('e-1')]);

    const stored = JSON.parse(sessionStorage.getItem(STORAGE_KEY)!);
    expect(stored).toHaveLength(1);
    expect(stored[0].id).toBe('e-1');
  });

  it('trims to the 50 most recent entries before writing', () => {
    const entries = Array.from({ length: 60 }, (_, i) => makeEntry(`e-${i}`));

    persistDebugMetricsHistory(entries);

    const stored = JSON.parse(sessionStorage.getItem(STORAGE_KEY)!);
    expect(stored).toHaveLength(50);
    expect(stored[0].id).toBe('e-10');
  });

  it('swallows storage errors (quota exceeded) without throwing', () => {
    vi.spyOn(Storage.prototype, 'setItem').mockImplementation(() => {
      throw new DOMException('QuotaExceededError');
    });

    expect(() => persistDebugMetricsHistory([makeEntry('e-1')])).not.toThrow();
  });
});
