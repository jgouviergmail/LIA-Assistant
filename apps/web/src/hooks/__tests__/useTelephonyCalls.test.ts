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

import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { renderHook, waitFor, act } from '@testing-library/react';

import { ApiError } from '@/lib/api-client';
import type { TelephonyCallSummary } from '@/types/telephony';

const { get } = vi.hoisted(() => ({ get: vi.fn() }));

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
    completed_at: '2026-07-26T09:01:02Z',
    ...overrides,
  };
}

beforeEach(() => {
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
    expect(get).toHaveBeenCalledWith('/telephony/calls');
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
