/**
 * useChatSuggestions — grounded suggestions, or silence.
 *
 * Two properties matter and neither is about the happy path: the request must
 * be SKIPPED where the rail cannot be shown (a busy chat must not pay for a
 * list nobody reads), and a failure must be indistinguishable from "nothing to
 * suggest" — both mean the generic starters appear, and an error banner on the
 * one screen a newcomer is unsure about would be noise.
 */

import { describe, it, expect, vi, beforeEach } from 'vitest';
import { renderHook } from '@testing-library/react';

const { mockUseApiQuery } = vi.hoisted(() => ({ mockUseApiQuery: vi.fn() }));
vi.mock('@/hooks/useApiQuery', () => ({ useApiQuery: mockUseApiQuery }));

import { useChatSuggestions } from '../useChatSuggestions';

function reply(over: Record<string, unknown> = {}) {
  return { data: undefined, loading: false, error: null, refetch: vi.fn(), setData: vi.fn(), ...over };
}

beforeEach(() => vi.clearAllMocks());

describe('useChatSuggestions', () => {
  it('returns what the server grounded', () => {
    mockUseApiQuery.mockReturnValue(
      reply({ data: { suggestions: [{ id: 'next_event', params: { subject: 'Revue' } }] } })
    );

    const { result } = renderHook(() => useChatSuggestions(true));

    expect(result.current.suggestions).toEqual([{ id: 'next_event', params: { subject: 'Revue' } }]);
  });

  it('asks the endpoint only when the rail can be shown', () => {
    mockUseApiQuery.mockReturnValue(reply());

    renderHook(() => useChatSuggestions(false));

    expect(mockUseApiQuery).toHaveBeenCalledWith(
      '/chat/suggestions',
      expect.objectContaining({ enabled: false })
    );
  });

  it('is empty while the first response is in flight', () => {
    mockUseApiQuery.mockReturnValue(reply({ loading: true }));

    const { result } = renderHook(() => useChatSuggestions(true));

    expect(result.current.suggestions).toEqual([]);
  });

  it('falls silent on failure rather than surfacing an error', () => {
    mockUseApiQuery.mockReturnValue(reply({ error: new Error('boom'), data: { suggestions: [{ id: 'x' }] } }));

    const { result } = renderHook(() => useChatSuggestions(true));

    // Even with stale data present: a failed grounding is not grounding.
    expect(result.current.suggestions).toEqual([]);
  });

  it('tolerates a payload without the array', () => {
    mockUseApiQuery.mockReturnValue(reply({ data: {} }));

    const { result } = renderHook(() => useChatSuggestions(true));

    expect(result.current.suggestions).toEqual([]);
  });
});
