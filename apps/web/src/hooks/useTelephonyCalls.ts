'use client';

/**
 * Recent outbound calls (A6).
 *
 * `GET /telephony/calls` has existed since the telephony domain shipped and was
 * consumed by nothing: the user confirmed a call, then saw nothing at all until
 * the post-call notification arrived. A missed notification meant the outcome
 * was unreachable — it sat in the database, with no surface to show it.
 *
 * Polling, and its honesty: there is NO intermediate webhook, only a post-call
 * one. So there is nothing to stream, and this hook does not pretend otherwise
 * — it re-reads the list while a call is in flight (`dialing` / `in_progress`)
 * and stops as soon as none is. An idle account issues exactly one request.
 */

import { useCallback, useEffect, useRef, useState } from 'react';

import { apiClient, ApiError } from '@/lib/api-client';
import { logger } from '@/lib/logger';
import { useStaleGuard } from '@/hooks/useStaleGuard';
import { ACTIVE_CALL_STATUSES, type TelephonyCallSummary } from '@/types/telephony';

/**
 * A call lasts minutes, and the only transition worth catching is its end.
 * Fast enough to feel live, slow enough to stay invisible in the logs.
 */
const ACTIVE_POLL_MS = 15_000;

export interface UseTelephonyCallsReturn {
  calls: TelephonyCallSummary[];
  /** True while a call is `dialing` or `in_progress`. */
  hasActiveCall: boolean;
  /** True only on the very first load. */
  isLoading: boolean;
  /** The feature is off (router absent → 404) — callers render nothing. */
  isUnavailable: boolean;
  refetch: () => Promise<void>;
}

/** Whether any call in the list is still happening. */
export function hasActiveCall(calls: readonly TelephonyCallSummary[]): boolean {
  return calls.some(call => ACTIVE_CALL_STATUSES.includes(call.status));
}

export function useTelephonyCalls(enabled = true, limit?: number): UseTelephonyCallsReturn {
  const [calls, setCalls] = useState<TelephonyCallSummary[]>([]);
  const [isLoading, setIsLoading] = useState(enabled);
  const [isUnavailable, setIsUnavailable] = useState(false);
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  // Staleness guard: a slow response must never overwrite a newer one, nor
  // commit state after unmount (audit F037 — shared, tested helper).
  const guard = useStaleGuard();

  const fetchCalls = useCallback(async () => {
    const isStale = guard.begin();
    try {
      // Ask the server for exactly what the caller displays — never fetch a
      // longer list to slice it client-side (the endpoint caps at 100).
      const endpoint =
        limit !== undefined ? `/telephony/calls?limit=${limit}` : '/telephony/calls';
      const response = await apiClient.get<TelephonyCallSummary[]>(endpoint);
      if (isStale()) return;
      setCalls(Array.isArray(response) ? response : []);
    } catch (error) {
      if (isStale()) return;
      // 404 = telephony disabled (router not registered). Not a failure: the
      // caller simply has nothing to show, and polling must stop for good.
      if (error instanceof ApiError && error.status === 404) {
        setIsUnavailable(true);
        setCalls([]);
        return;
      }
      // A backend that is merely unreachable (startup, restart) is expected
      // noise here — the next tick retries.
      if (error instanceof TypeError) return;
      logger.error('Failed to fetch telephony calls', error as Error, {
        component: 'useTelephonyCalls',
      });
    } finally {
      if (!isStale()) setIsLoading(false);
    }
  }, [guard, limit]);

  useEffect(() => {
    if (!enabled || isUnavailable) {
      setIsLoading(false);
      return;
    }
    void fetchCalls();
  }, [enabled, isUnavailable, fetchCalls]);

  // Poll ONLY while something is in flight; a finished list is static, and
  // re-reading it forever would be pure noise on every idle account.
  const active = hasActiveCall(calls);
  useEffect(() => {
    if (!enabled || isUnavailable || !active) return;
    timerRef.current = setTimeout(() => void fetchCalls(), ACTIVE_POLL_MS);
    return () => {
      if (timerRef.current) clearTimeout(timerRef.current);
      timerRef.current = null;
    };
    // `calls` is in the deps through `active` AND through the identity of the
    // list: each fetch reschedules the next tick.
  }, [enabled, isUnavailable, active, calls, fetchCalls]);

  return { calls, hasActiveCall: active, isLoading, isUnavailable, refetch: fetchCalls };
}
