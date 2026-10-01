/**
 * useRecipientSuggestions — one request per pause in typing, and only the
 * answer to what is typed now.
 */

import { act, renderHook } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

const { query } = vi.hoisted(() => ({ query: vi.fn() }));
vi.mock('@/hooks/useApiQuery', () => ({ useApiQuery: query }));

import {
  RECIPIENT_SUGGESTIONS_DEBOUNCE_MS,
  useRecipientSuggestions,
} from '../useRecipientSuggestions';

const JEAN = { name: 'Jean', email: 'jean@example.org' };

beforeEach(() => {
  vi.useFakeTimers();
  query.mockImplementation((_endpoint: string, options: { params?: { q?: string } }) => ({
    data: { query: options.params?.q, suggestions: [JEAN], truncated: false },
    loading: false,
    error: null,
    refetch: vi.fn(),
  }));
});

afterEach(() => {
  vi.useRealTimers();
  vi.clearAllMocks();
});

function lastAsk(): { enabled?: boolean; params?: { q?: string } } {
  return query.mock.calls[query.mock.calls.length - 1][1];
}

describe('useRecipientSuggestions', () => {
  it('asks only once the typing has paused', () => {
    const { rerender } = renderHook(({ q }) => useRecipientSuggestions(q, true, 2), {
      initialProps: { q: 'je' },
    });
    act(() => vi.advanceTimersByTime(RECIPIENT_SUGGESTIONS_DEBOUNCE_MS));
    expect(lastAsk()).toMatchObject({ enabled: true, params: { q: 'je' } });

    rerender({ q: 'jea' });
    // Typed, not yet settled: the previous query is not re-asked for the new text.
    expect(lastAsk().enabled).toBe(false);

    act(() => vi.advanceTimersByTime(RECIPIENT_SUGGESTIONS_DEBOUNCE_MS));
    expect(lastAsk()).toMatchObject({ enabled: true, params: { q: 'jea' } });
  });

  it('returns nothing while the answer in hand is to another query', () => {
    const { result, rerender } = renderHook(({ q }) => useRecipientSuggestions(q, true, 2), {
      initialProps: { q: 'jea' },
    });
    act(() => vi.advanceTimersByTime(RECIPIENT_SUGGESTIONS_DEBOUNCE_MS));
    expect(result.current.suggestions).toEqual([JEAN]);

    query.mockImplementation(() => ({
      data: { query: 'jea', suggestions: [JEAN], truncated: false },
      loading: false,
      error: null,
      refetch: vi.fn(),
    }));
    rerender({ q: 'jean' });

    expect(result.current.suggestions).toEqual([]);
  });

  it('asks nothing when the account has no suggestions, or below the minimum', () => {
    const { result } = renderHook(() => useRecipientSuggestions('jea', false, 2));
    act(() => vi.advanceTimersByTime(RECIPIENT_SUGGESTIONS_DEBOUNCE_MS));
    expect(lastAsk().enabled).toBe(false);
    expect(result.current.suggestions).toEqual([]);

    renderHook(() => useRecipientSuggestions('j', true, 2));
    act(() => vi.advanceTimersByTime(RECIPIENT_SUGGESTIONS_DEBOUNCE_MS));
    expect(lastAsk().enabled).toBe(false);
  });
});
