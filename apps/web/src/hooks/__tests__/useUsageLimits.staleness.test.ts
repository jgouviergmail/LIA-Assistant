/**
 * useUsageLimits — staleness guard (audit F037).
 *
 * The polling hook must never let a slow, out-of-order response overwrite a
 * newer one. Before the fix, an in-flight request that resolved late clobbered
 * the fresh state; now each fetch carries a monotonic id and only the latest
 * (while mounted) commits.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { renderHook, act, waitFor } from '@testing-library/react';

const h = vi.hoisted(() => ({ get: vi.fn() }));

vi.mock('@/lib/api-client', () => ({
  apiClient: { get: (...args: unknown[]) => h.get(...args) },
  ApiError: class ApiError extends Error {
    status: number;
    constructor(status: number) {
      super(`ApiError ${status}`);
      this.status = status;
    }
  },
}));

vi.mock('@/lib/logger', () => ({
  logger: { error: vi.fn(), debug: vi.fn(), info: vi.fn(), warn: vi.fn() },
}));

import { useUsageLimits } from '../useUsageLimits';

function deferred<T>() {
  let resolve!: (value: T) => void;
  const promise = new Promise<T>(r => {
    resolve = r;
  });
  return { promise, resolve };
}

const makeLimits = (reason: string) => ({
  is_blocked: reason !== 'A',
  blocked_reason: reason,
});

describe('useUsageLimits staleness guard (F037)', () => {
  beforeEach(() => {
    h.get.mockReset();
  });

  it('drops an out-of-order stale response — the latest request wins', async () => {
    const first = deferred<ReturnType<typeof makeLimits>>();
    const second = deferred<ReturnType<typeof makeLimits>>();
    // Call 1 (initial mount) → first; call 2 (refetch) → second.
    h.get.mockReturnValueOnce(first.promise).mockReturnValueOnce(second.promise);

    const { result } = renderHook(() => useUsageLimits());

    await act(async () => {
      result.current.refetch();
    });

    // Resolve the NEWER request first, then the older/stale one.
    await act(async () => {
      second.resolve(makeLimits('B'));
    });
    await act(async () => {
      first.resolve(makeLimits('A'));
    });

    // The stale 'A' must NOT overwrite the newer 'B'.
    expect(result.current.limits?.blocked_reason).toBe('B');
  });

  it('an older request finishing first must NOT clear the newer one loading (F037)', async () => {
    const first = deferred<ReturnType<typeof makeLimits>>();
    const second = deferred<ReturnType<typeof makeLimits>>();
    // Call 1 (mount) → first; call 2 (refetch) → second. Both in flight.
    h.get.mockReturnValueOnce(first.promise).mockReturnValueOnce(second.promise);

    const { result } = renderHook(() => useUsageLimits());
    await act(async () => {
      result.current.refetch();
    });
    expect(result.current.isLoading).toBe(true);

    // The OLDER request resolves first — its finally must not clear loading,
    // because the newer request is still pending.
    await act(async () => {
      first.resolve(makeLimits('A'));
    });
    expect(result.current.isLoading).toBe(true);

    // The newer (current) request resolves → loading clears.
    await act(async () => {
      second.resolve(makeLimits('B'));
    });
    expect(result.current.isLoading).toBe(false);
  });

  it('exposes limits on a normal fetch', async () => {
    h.get.mockResolvedValue(makeLimits('blocked-quota'));
    const { result } = renderHook(() => useUsageLimits());
    await waitFor(() => expect(result.current.limits).not.toBeNull());
    expect(result.current.limits?.blocked_reason).toBe('blocked-quota');
    expect(result.current.isBlocked).toBe(true);
  });
});
