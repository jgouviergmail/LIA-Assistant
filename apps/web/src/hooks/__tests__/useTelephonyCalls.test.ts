/**
 * Recent outbound calls (A6).
 *
 * The endpoint existed and nothing consumed it. What this hook must get right:
 *
 *  - it polls ONLY while a call is in flight. An idle account issuing a request
 *    every 15 s forever would be pure waste, on every session, for nothing;
 *  - a disabled feature (404) is not an error — it silences the hook for good
 *    rather than retrying a route that will never exist;
 *  - it never claims more than the backend offers: there is no intermediate
 *    webhook, so this is a refresh, not a stream.
 */

import { createElement, StrictMode, type PropsWithChildren } from 'react';
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { renderHook, waitFor, act } from '@testing-library/react';

import { ApiError } from '@/lib/api-client';
import type { TelephonyCallSummary } from '@/types/telephony';

const { get, auth } = vi.hoisted(() => ({
  get: vi.fn(),
  auth: { owner: 'one' as string | undefined },
}));

vi.mock('@/hooks/useAuth', () => ({
  useAuth: () => ({ user: auth.owner ? { id: auth.owner } : null }),
}));

vi.mock('@/lib/api-client', async importOriginal => {
  const actual = await importOriginal<typeof import('@/lib/api-client')>();
  return { ...actual, apiClient: { get } };
});

vi.mock('@/lib/logger', () => ({
  logger: { error: vi.fn(), warn: vi.fn(), info: vi.fn(), debug: vi.fn() },
}));

import { useTelephonyCalls, hasActiveCall } from '../useTelephonyCalls';

function call(overrides: Partial<TelephonyCallSummary> = {}): TelephonyCallSummary {
  return {
    id: 'c1',
    callee_display: 'Marie',
    objective: 'Demander si elle est libre mardi',
    status: 'completed',
    outcome: 'objective_met',
    summary: 'Marie est libre mardi après 14h.',
    debrief: null,
    call_seconds: 62,
    created_at: '2026-07-26T09:00:00Z',
    call_kind: 'third_party',
    call_mode: 'direct',
    relay_outcome: null,
    completed_at: '2026-07-26T09:01:02Z',
    ...overrides,
  };
}

beforeEach(() => {
  auth.owner = 'one';
  get.mockReset();
  vi.useFakeTimers({ shouldAdvanceTime: true });
});

afterEach(() => {
  vi.useRealTimers();
});

describe('hasActiveCall', () => {
  it('recognises a call that is still happening', () => {
    expect(hasActiveCall([call({ status: 'dialing' })])).toBe(true);
    expect(hasActiveCall([call({ status: 'in_progress' })])).toBe(true);
  });

  it('treats every terminal status as finished', () => {
    for (const status of ['completed', 'no_answer', 'voicemail', 'failed', 'cancelled'] as const) {
      expect(hasActiveCall([call({ status })]), status).toBe(false);
    }
  });

  it('is false on an empty list', () => {
    expect(hasActiveCall([])).toBe(false);
  });
});

describe('useTelephonyCalls', () => {
  it('reads the calls once on mount', async () => {
    get.mockResolvedValue([call()]);
    const { result } = renderHook(() => useTelephonyCalls());

    await waitFor(() => expect(result.current.isLoading).toBe(false));
    expect(result.current.calls).toHaveLength(1);
    expect(get).toHaveBeenCalledWith(
      '/telephony/calls',
      expect.objectContaining({ signal: expect.any(AbortSignal) })
    );
  });

  it('asks the server for exactly the requested window when a limit is given', async () => {
    get.mockResolvedValue([call()]);
    const { result } = renderHook(() => useTelephonyCalls(true, 10));

    await waitFor(() => expect(result.current.isLoading).toBe(false));
    expect(get).toHaveBeenCalledWith(
      '/telephony/calls?limit=10',
      expect.objectContaining({ signal: expect.any(AbortSignal) })
    );
  });

  it('does not poll an idle account', async () => {
    // The whole point: a finished list is static. Re-reading it forever would
    // be noise on every session of every user.
    get.mockResolvedValue([call({ status: 'completed' })]);
    const { result } = renderHook(() => useTelephonyCalls());
    await waitFor(() => expect(result.current.isLoading).toBe(false));

    await act(async () => {
      await vi.advanceTimersByTimeAsync(60_000);
    });

    expect(get).toHaveBeenCalledTimes(1);
  });

  it('refreshes while a call is in flight', async () => {
    get.mockResolvedValue([call({ status: 'in_progress' })]);
    const { result } = renderHook(() => useTelephonyCalls());
    await waitFor(() => expect(result.current.hasActiveCall).toBe(true));

    await act(async () => {
      await vi.advanceTimersByTimeAsync(16_000);
    });

    expect(get.mock.calls.length).toBeGreaterThan(1);
  });

  it('stops refreshing once the call ends', async () => {
    get.mockResolvedValueOnce([call({ status: 'dialing' })]);
    get.mockResolvedValue([call({ status: 'completed' })]);
    const { result } = renderHook(() => useTelephonyCalls());

    await waitFor(() => expect(result.current.hasActiveCall).toBe(true));
    await act(async () => {
      await vi.advanceTimersByTimeAsync(16_000);
    });
    await waitFor(() => expect(result.current.hasActiveCall).toBe(false));

    const afterSettle = get.mock.calls.length;
    await act(async () => {
      await vi.advanceTimersByTimeAsync(60_000);
    });
    expect(get.mock.calls.length).toBe(afterSettle);
  });

  it('goes quiet for good when the feature is disabled', async () => {
    // 404 = router not registered. Retrying a route that will never exist
    // would log an error on every tick.
    get.mockRejectedValue(new ApiError('not found', 404));
    const { result } = renderHook(() => useTelephonyCalls());

    await waitFor(() => expect(result.current.isUnavailable).toBe(true));
    expect(result.current.calls).toEqual([]);
    expect(result.current.isLoading).toBe(false);

    await act(async () => {
      await vi.advanceTimersByTimeAsync(60_000);
    });
    expect(get).toHaveBeenCalledTimes(1);
  });

  it('keeps the previous list when a refresh fails', async () => {
    // A transient error must not blank a surface the user is reading.
    get.mockResolvedValueOnce([call({ status: 'in_progress' })]);
    get.mockRejectedValue(new ApiError('boom', 500));
    const { result } = renderHook(() => useTelephonyCalls());
    await waitFor(() => expect(result.current.calls).toHaveLength(1));

    await act(async () => {
      await vi.advanceTimersByTimeAsync(16_000);
    });

    expect(result.current.calls).toHaveLength(1);
  });

  it('survives a malformed payload', async () => {
    // Defensive: the surface must never crash on an unexpected shape.
    get.mockResolvedValue({ unexpected: true });
    const { result } = renderHook(() => useTelephonyCalls());

    await waitFor(() => expect(result.current.isLoading).toBe(false));
    expect(result.current.calls).toEqual([]);
  });

  it('does nothing at all when disabled by its caller', async () => {
    renderHook(() => useTelephonyCalls(false));
    await act(async () => {
      await vi.advanceTimersByTimeAsync(30_000);
    });
    expect(get).not.toHaveBeenCalled();
  });
});

function deferred<T>() {
  let resolve!: (value: T) => void;
  const promise = new Promise<T>(complete => {
    resolve = complete;
  });
  return { promise, resolve };
}

describe('useTelephonyCalls request ownership and recovery', () => {
  it('exposes a server error, then recovers on an explicit retry', async () => {
    const failure = new ApiError('Unavailable', 503);
    get.mockRejectedValueOnce(failure).mockResolvedValueOnce([call()]);
    const { result } = renderHook(() => useTelephonyCalls());
    await waitFor(() => expect(result.current.isLoading).toBe(false));
    expect(result.current.error).toBe(failure);
    expect(result.current.calls).toEqual([]);
    expect(result.current.isUnavailable).toBe(false);
    await act(async () => {
      await result.current.refetch();
    });
    expect(result.current.calls).toHaveLength(1);
    expect(result.current.error).toBeNull();
  });

  it('exposes transport failures rather than presenting an empty history', async () => {
    const failure = new TypeError('Failed to fetch');
    get.mockRejectedValueOnce(failure);
    const { result } = renderHook(() => useTelephonyCalls());
    await waitFor(() => expect(result.current.isLoading).toBe(false));
    expect(result.current.error).toBe(failure);
  });

  it('keeps loaded content and the first-load state stable through a failed refresh', async () => {
    const pending = deferred<TelephonyCallSummary[]>();
    get.mockResolvedValueOnce([call()]).mockReturnValueOnce(pending.promise);
    const { result } = renderHook(() => useTelephonyCalls());
    await waitFor(() => expect(result.current.calls).toHaveLength(1));
    let refresh!: Promise<void>;
    act(() => {
      refresh = result.current.refetch();
    });
    expect(result.current.isLoading).toBe(false);
    expect(result.current.calls).toHaveLength(1);
    await act(async () => {
      pending.resolve([call({ summary: 'Updated' })]);
      await refresh;
    });
    get.mockRejectedValueOnce(new ApiError('Offline', 503));
    await act(async () => {
      await result.current.refetch();
    });
    expect(result.current.calls[0].summary).toBe('Updated');
    expect(result.current.isLoading).toBe(false);
    expect(result.current.error).toBeInstanceOf(ApiError);
  });

  it('retries a failed active poll after another interval', async () => {
    get.mockResolvedValueOnce([call({ status: 'in_progress' })]);
    get.mockRejectedValueOnce(new ApiError('Offline', 503));
    get.mockResolvedValueOnce([call()]);
    const { result } = renderHook(() => useTelephonyCalls());
    await waitFor(() => expect(result.current.hasActiveCall).toBe(true));
    await act(async () => {
      await vi.advanceTimersByTimeAsync(15_000);
    });
    expect(result.current.error).toBeInstanceOf(ApiError);
    expect(result.current.hasActiveCall).toBe(true);
    await act(async () => {
      await vi.advanceTimersByTimeAsync(15_000);
    });
    expect(get).toHaveBeenCalledTimes(3);
    expect(result.current.hasActiveCall).toBe(false);
    expect(result.current.error).toBeNull();
  });

  it('does not poll while an active request is still pending', async () => {
    const pending = deferred<TelephonyCallSummary[]>();
    get.mockResolvedValueOnce([call({ status: 'dialing' })]).mockReturnValueOnce(pending.promise);
    const { result } = renderHook(() => useTelephonyCalls());
    await waitFor(() => expect(result.current.hasActiveCall).toBe(true));
    await act(async () => {
      await vi.advanceTimersByTimeAsync(75_000);
    });
    expect(get).toHaveBeenCalledTimes(2);
    await act(async () => {
      pending.resolve([call()]);
    });
    expect(result.current.hasActiveCall).toBe(false);
  });

  it('hides an old account and rejects its late response and retained retry', async () => {
    const old = deferred<TelephonyCallSummary[]>();
    const fresh = deferred<TelephonyCallSummary[]>();
    get
      .mockResolvedValueOnce([call({ callee_display: 'Private one' })])
      .mockReturnValueOnce(old.promise)
      .mockReturnValueOnce(fresh.promise);
    const { result, rerender } = renderHook(() => useTelephonyCalls());
    await waitFor(() => expect(result.current.calls).toHaveLength(1));
    const obsoleteRetry = result.current.refetch;
    act(() => {
      void result.current.refetch();
    });
    const oldSignal: AbortSignal = get.mock.calls[1][1].signal;
    auth.owner = 'two';
    rerender();
    expect(result.current.calls).toEqual([]);
    expect(result.current.error).toBeNull();
    expect(oldSignal.aborted).toBe(true);
    await act(async () => {
      old.resolve([call({ callee_display: 'Late private one' })]);
      await obsoleteRetry();
    });
    expect(result.current.calls).toEqual([]);
    expect(get).toHaveBeenCalledTimes(3);
    await act(async () => {
      fresh.resolve([call({ callee_display: 'Public two' })]);
    });
    expect(result.current.calls[0].callee_display).toBe('Public two');
  });

  it('starts fresh on A-to-B-to-A without resurrecting the old unavailable state', async () => {
    get.mockRejectedValueOnce(new ApiError('Absent', 404));
    get.mockResolvedValueOnce([call({ callee_display: 'Owner two' })]);
    const returned = deferred<TelephonyCallSummary[]>();
    get.mockReturnValueOnce(returned.promise);
    const { result, rerender } = renderHook(() => useTelephonyCalls());
    await waitFor(() => expect(result.current.isUnavailable).toBe(true));
    auth.owner = 'two';
    rerender();
    await waitFor(() => expect(result.current.calls[0]?.callee_display).toBe('Owner two'));
    auth.owner = 'one';
    rerender();
    expect(result.current.calls).toEqual([]);
    expect(result.current.isUnavailable).toBe(false);
    await act(async () => {
      returned.resolve([call({ callee_display: 'Owner one now' })]);
    });
    expect(result.current.calls[0].callee_display).toBe('Owner one now');
  });

  it('invalidates old endpoint responses and callbacks when the limit changes', async () => {
    const old = deferred<TelephonyCallSummary[]>();
    const fresh = deferred<TelephonyCallSummary[]>();
    get.mockReturnValueOnce(old.promise).mockReturnValueOnce(fresh.promise);
    const { result, rerender } = renderHook(({ limit }) => useTelephonyCalls(true, limit), {
      initialProps: { limit: 10 },
    });
    const obsoleteRetry = result.current.refetch;
    await waitFor(() => expect(get).toHaveBeenCalledTimes(1));
    const oldSignal: AbortSignal = get.mock.calls[0][1].signal;
    rerender({ limit: 20 });
    expect(oldSignal.aborted).toBe(true);
    await act(async () => {
      old.resolve([call({ callee_display: 'Wrong window' })]);
      await obsoleteRetry();
    });
    expect(result.current.calls).toEqual([]);
    expect(get).toHaveBeenCalledTimes(2);
    await act(async () => {
      fresh.resolve([call({ callee_display: 'Correct window' })]);
    });
    expect(result.current.calls[0].callee_display).toBe('Correct window');
  });

  it('silences transport and retained callbacks on disable or logout', async () => {
    get.mockResolvedValue([call({ status: 'dialing' })]);
    const { result, rerender } = renderHook(({ enabled }) => useTelephonyCalls(enabled), {
      initialProps: { enabled: true },
    });
    await waitFor(() => expect(result.current.calls).toHaveLength(1));
    const obsoleteRetry = result.current.refetch;
    rerender({ enabled: false });
    expect(result.current.calls).toEqual([]);
    expect(result.current.isLoading).toBe(false);
    await act(async () => {
      await result.current.refetch();
      await obsoleteRetry();
      await vi.advanceTimersByTimeAsync(60_000);
    });
    expect(get).toHaveBeenCalledTimes(1);
    auth.owner = undefined;
    rerender({ enabled: true });
    await act(async () => {
      await result.current.refetch();
      await vi.advanceTimersByTimeAsync(60_000);
    });
    expect(get).toHaveBeenCalledTimes(1);
  });

  it('aborts superseded and unmounted reads and ignores their late responses', async () => {
    const old = deferred<TelephonyCallSummary[]>();
    get
      .mockReturnValueOnce(old.promise)
      .mockResolvedValueOnce([call({ callee_display: 'Current' })]);
    const { result, unmount } = renderHook(() => useTelephonyCalls());
    await waitFor(() => expect(get).toHaveBeenCalledTimes(1));
    const firstSignal: AbortSignal = get.mock.calls[0][1].signal;
    await act(async () => {
      await result.current.refetch();
    });
    expect(firstSignal.aborted).toBe(true);
    await act(async () => {
      old.resolve([call({ callee_display: 'Obsolete' })]);
    });
    expect(result.current.calls[0].callee_display).toBe('Current');
    const pending = deferred<TelephonyCallSummary[]>();
    get.mockReturnValueOnce(pending.promise);
    const retained = result.current.refetch;
    act(() => {
      void retained();
    });
    const lastSignal: AbortSignal = get.mock.calls[2][1].signal;
    unmount();
    expect(lastSignal.aborted).toBe(true);
    await act(async () => {
      pending.resolve([]);
      await retained();
    });
    expect(get).toHaveBeenCalledTimes(3);
  });

  it('does not let manual retries revive an unavailable feature', async () => {
    get.mockRejectedValue(new ApiError('Absent', 404));
    const { result } = renderHook(() => useTelephonyCalls());
    await waitFor(() => expect(result.current.isUnavailable).toBe(true));
    await act(async () => {
      await result.current.refetch();
    });
    expect(get).toHaveBeenCalledTimes(1);
    expect(result.current.error).toBeNull();
  });
});

describe('useTelephonyCalls effect IO lifetime', () => {
  it('sends only one initial request under the Strict Mode setup probe', async () => {
    get.mockResolvedValue([call()]);
    const wrapper = ({ children }: PropsWithChildren) => createElement(StrictMode, null, children);
    const { result } = renderHook(() => useTelephonyCalls(), { wrapper });
    await waitFor(() => expect(result.current.calls).toHaveLength(1));
    expect(get).toHaveBeenCalledTimes(1);
    await act(async () => {
      await vi.advanceTimersByTimeAsync(30_000);
    });
    expect(get).toHaveBeenCalledTimes(1);
  });

  it('does not send a deferred initial read after an immediate unmount', async () => {
    const { result, unmount } = renderHook(() => useTelephonyCalls());
    const retained = result.current.refetch;
    unmount();
    await act(async () => {
      await Promise.resolve();
      await retained();
    });
    expect(get).not.toHaveBeenCalled();
  });
});
