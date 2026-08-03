/**
 * usePersonalResults — the figures behind "what LIA achieved".
 *
 * The property worth pinning is the loading flag: derived from the ABSENCE of
 * data, never from `error`. A refetch clears the error, and a spinner keyed on
 * it would unmount the block mid-refresh (the `PeerConnectionsSettings` defect
 * the frontend guide documents).
 */

import { describe, it, expect, vi, beforeEach } from 'vitest';
import { renderHook } from '@testing-library/react';

const { mockUseApiQuery } = vi.hoisted(() => ({ mockUseApiQuery: vi.fn() }));
vi.mock('@/hooks/useApiQuery', () => ({ useApiQuery: mockUseApiQuery }));

import { usePersonalResults } from '../usePersonalResults';

const RESULTS = {
  cycle_start: '2026-08-01T00:00:00Z',
  useful_results: 12,
  actions: 5,
  automations: 3,
  commitments_closed: 2,
  measured: true,
};

function reply(over: Record<string, unknown> = {}) {
  return { data: undefined, loading: false, error: null, refetch: vi.fn(), setData: vi.fn(), ...over };
}

beforeEach(() => vi.clearAllMocks());

describe('usePersonalResults', () => {
  it('exposes the figures once loaded', () => {
    mockUseApiQuery.mockReturnValue(reply({ data: RESULTS }));

    const { result } = renderHook(() => usePersonalResults());

    expect(result.current.results).toEqual(RESULTS);
    expect(result.current.firstLoad).toBe(false);
  });

  it('reports a first load only while there is no data at all', () => {
    mockUseApiQuery.mockReturnValue(reply({ loading: true }));

    const { result } = renderHook(() => usePersonalResults());

    expect(result.current.firstLoad).toBe(true);
  });

  it('is NOT a first load while refreshing existing figures', () => {
    // `loading` is true again on a refetch; the block must stay mounted.
    mockUseApiQuery.mockReturnValue(reply({ data: RESULTS, loading: true }));

    const { result } = renderHook(() => usePersonalResults());

    expect(result.current.firstLoad).toBe(false);
    expect(result.current.results).toEqual(RESULTS);
  });

  it('surfaces the error so the caller can stay absent rather than show zeros', () => {
    const error = new Error('boom');
    mockUseApiQuery.mockReturnValue(reply({ error }));

    const { result } = renderHook(() => usePersonalResults());

    expect(result.current.error).toBe(error);
    expect(result.current.results).toBeUndefined();
  });
});
