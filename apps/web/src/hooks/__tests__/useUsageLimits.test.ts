/**
 * Unit tests for `useUsageLimits` (audit F010, risk-first).
 *
 * Drives the polling usage-limits hook with a mocked `apiClient.get` (the real
 * `ApiError` class is kept so the 404 branch is exercised faithfully) and the
 * real `useStaleGuard`. Covers success + derived flags, the 404 feature-disable
 * path (polling stops), the silent-network-error and logged-error branches,
 * the 60s polling tick, manual refetch, and unmount cleanup.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { renderHook, waitFor, act } from '@testing-library/react';

const mockGet = vi.hoisted(() => vi.fn());

vi.mock('@/lib/api-client', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/lib/api-client')>();
  return { ...actual, apiClient: { get: mockGet } };
});
vi.mock('@/lib/logger', () => ({
  logger: { debug: vi.fn(), info: vi.fn(), warn: vi.fn(), error: vi.fn() },
}));

import { useUsageLimits } from '../useUsageLimits';
import { ApiError } from '@/lib/api-client';
import { logger } from '@/lib/logger';
import type { UserUsageLimitResponse } from '@/types/usage-limits';

function makeLimits(over: Partial<UserUsageLimitResponse> = {}): UserUsageLimitResponse {
  return { is_blocked: false, blocked_reason: null, ...over } as UserUsageLimitResponse;
}

beforeEach(() => {
  vi.clearAllMocks();
});
afterEach(() => {
  vi.clearAllMocks();
  vi.useRealTimers();
});

describe('useUsageLimits', () => {
  it('exposes limits and derived flags on success', async () => {
    mockGet.mockResolvedValue(makeLimits({ is_blocked: true, blocked_reason: 'quota' }));

    const { result } = renderHook(() => useUsageLimits());

    await waitFor(() => expect(result.current.isLoading).toBe(false));
    expect(result.current.limits).toEqual(makeLimits({ is_blocked: true, blocked_reason: 'quota' }));
    expect(result.current.isBlocked).toBe(true);
    expect(result.current.blockReason).toBe('quota');
    expect(mockGet).toHaveBeenCalledWith('/usage-limits/me');
  });

  it('defaults isBlocked/blockReason to false/null when not blocked', async () => {
    mockGet.mockResolvedValue(makeLimits());
    const { result } = renderHook(() => useUsageLimits());
    await waitFor(() => expect(result.current.isLoading).toBe(false));
    expect(result.current.isBlocked).toBe(false);
    expect(result.current.blockReason).toBeNull();
  });

  it('treats a 404 as feature-disabled and stops polling', async () => {
    vi.useFakeTimers();
    mockGet.mockRejectedValue(new ApiError('not found', 404));

    const { result } = renderHook(() => useUsageLimits());
    // Flush the initial fetch's rejection + resulting state updates. waitFor is
    // unusable here (it relies on real timers that never advance under fake ones).
    await act(async () => {
      await vi.advanceTimersByTimeAsync(0);
    });

    expect(result.current.isLoading).toBe(false);
    expect(result.current.limits).toBeNull();
    expect(mockGet).toHaveBeenCalledTimes(1);

    // Polling must have been cancelled: advancing well past the interval and a
    // manual refetch both make no further request (featureDisabled short-circuit).
    await act(async () => {
      await vi.advanceTimersByTimeAsync(200_000);
    });
    await act(async () => {
      await result.current.refetch();
    });
    expect(mockGet).toHaveBeenCalledTimes(1);
  });

  it('swallows network TypeErrors without logging', async () => {
    mockGet.mockRejectedValue(new TypeError('Failed to fetch'));
    const { result } = renderHook(() => useUsageLimits());
    await waitFor(() => expect(result.current.isLoading).toBe(false));
    expect(result.current.limits).toBeNull();
    expect(logger.error).not.toHaveBeenCalled();
  });

  it('logs unexpected (non-404, non-network) errors', async () => {
    mockGet.mockRejectedValue(new ApiError('boom', 500));
    const { result } = renderHook(() => useUsageLimits());
    await waitFor(() => expect(result.current.isLoading).toBe(false));
    expect(logger.error).toHaveBeenCalledWith(
      'Failed to fetch usage limits',
      expect.any(ApiError),
      expect.objectContaining({ component: 'useUsageLimits' })
    );
  });

  it('polls again after the 60s interval', async () => {
    vi.useFakeTimers();
    mockGet.mockResolvedValue(makeLimits());
    renderHook(() => useUsageLimits());

    await act(async () => {
      await Promise.resolve();
    });
    expect(mockGet).toHaveBeenCalledTimes(1);

    await act(async () => {
      await vi.advanceTimersByTimeAsync(60_000);
    });
    expect(mockGet).toHaveBeenCalledTimes(2);
  });

  it('refetches on demand', async () => {
    mockGet.mockResolvedValue(makeLimits());
    const { result } = renderHook(() => useUsageLimits());
    await waitFor(() => expect(result.current.isLoading).toBe(false));

    await act(async () => {
      await result.current.refetch();
    });
    expect(mockGet).toHaveBeenCalledTimes(2);
  });

  it('clears the polling interval on unmount', async () => {
    vi.useFakeTimers();
    mockGet.mockResolvedValue(makeLimits());
    const { unmount } = renderHook(() => useUsageLimits());
    await act(async () => {
      await Promise.resolve();
    });
    expect(mockGet).toHaveBeenCalledTimes(1);

    unmount();
    await act(async () => {
      await vi.advanceTimersByTimeAsync(120_000);
    });
    // No further polls after unmount.
    expect(mockGet).toHaveBeenCalledTimes(1);
  });
});
