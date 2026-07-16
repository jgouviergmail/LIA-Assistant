/**
 * Unit tests for `useUserStatistics`.
 *
 * Drives the raw-fetch polling hook with a mocked `useAuth` (auth gate),
 * `logging-context` and logger, and a stubbed global `fetch`. Covers the
 * success path, HTTP-error and thrown-error paths, and the no-user short
 * circuit (no request, loading cleared). The real `useStaleGuard` is used.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { renderHook, waitFor } from '@testing-library/react';

const mockUseAuth = vi.hoisted(() => vi.fn());

vi.mock('@/hooks/useAuth', () => ({ useAuth: mockUseAuth }));
vi.mock('@/lib/logging-context', () => ({
  useLoggingContext: () => ({ withContext: (o: Record<string, unknown>) => o }),
}));
vi.mock('@/lib/logger', () => ({
  logger: { debug: vi.fn(), info: vi.fn(), warn: vi.fn(), error: vi.fn() },
}));

import { useUserStatistics } from '../useUserStatistics';

const STATS = {
  total_messages: 42,
  cycle_messages: 7,
  total_cost_eur: 1.23,
};

beforeEach(() => {
  vi.clearAllMocks();
  mockUseAuth.mockReturnValue({ user: { id: 'u1' } });
});
afterEach(() => {
  vi.clearAllMocks();
  vi.unstubAllGlobals();
});

describe('useUserStatistics', () => {
  it('fetches and exposes statistics on success', async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      json: () => Promise.resolve(STATS),
    });
    vi.stubGlobal('fetch', fetchMock);

    const { result } = renderHook(() => useUserStatistics());

    await waitFor(() => expect(result.current.isLoading).toBe(false));
    expect(result.current.statistics).toEqual(STATS);
    expect(result.current.error).toBeNull();
    expect(fetchMock.mock.calls[0][0]).toContain('/chat/users/me/statistics');
  });

  it('surfaces an error on a non-ok response', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue({ ok: false, status: 500, statusText: 'Server Error' })
    );

    const { result } = renderHook(() => useUserStatistics());

    await waitFor(() => expect(result.current.error).not.toBeNull());
    expect(result.current.error).toContain('500');
    expect(result.current.statistics).toBeNull();
    expect(result.current.isLoading).toBe(false);
  });

  it('surfaces an error when fetch rejects', async () => {
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new Error('network down')));

    const { result } = renderHook(() => useUserStatistics());

    await waitFor(() => expect(result.current.error).toBe('network down'));
    expect(result.current.isLoading).toBe(false);
  });

  it('does not fetch when there is no authenticated user', async () => {
    mockUseAuth.mockReturnValue({ user: null });
    const fetchMock = vi.fn();
    vi.stubGlobal('fetch', fetchMock);

    const { result } = renderHook(() => useUserStatistics());

    await waitFor(() => expect(result.current.isLoading).toBe(false));
    expect(fetchMock).not.toHaveBeenCalled();
    expect(result.current.statistics).toBeNull();
  });
});
