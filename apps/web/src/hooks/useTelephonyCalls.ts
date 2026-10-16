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

import { useCallback, useEffect, useRef } from 'react';

import { apiClient, ApiError } from '@/lib/api-client';
import { logger } from '@/lib/logger';
import { useAuth } from '@/hooks/useAuth';
import { useApplicationAccountLifetime } from '@/hooks/useApplicationAccountLifetime';
import { useApplicationAccountState } from '@/hooks/useApplicationAccountState';
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
  /** A current read failed; an already loaded history remains visible. */
  error: Error | null;
  refetch: () => Promise<void>;
}

/** Whether any call in the list is still happening. */
export function hasActiveCall(calls: readonly TelephonyCallSummary[]): boolean {
  return calls.some(call => ACTIVE_CALL_STATUSES.includes(call.status));
}

interface CallsState {
  calls: TelephonyCallSummary[];
  error: Error | null;
  unavailable: boolean;
  settled: boolean;
  busy: boolean;
}

const INITIAL_STATE: CallsState = {
  calls: [],
  error: null,
  unavailable: false,
  settled: false,
  busy: false,
};

export function useTelephonyCalls(enabled = true, limit?: number): UseTelephonyCallsReturn {
  const { user } = useAuth();
  const endpoint = limit !== undefined ? `/telephony/calls?limit=${limit}` : '/telephony/calls';
  const scope = enabled && user?.id ? JSON.stringify([user.id, endpoint]) : undefined;
  const { isCurrent } = useApplicationAccountLifetime(scope);
  const [state, setState] = useApplicationAccountState(scope, INITIAL_STATE);
  const activeRequest = useRef<AbortController | null>(null);

  const fetchCalls = useCallback(
    async (lifetime: AbortSignal) => {
      if (!isCurrent() || lifetime.aborted || state.unavailable) return;
      activeRequest.current?.abort();
      const request = new AbortController();
      activeRequest.current = request;
      const signal = AbortSignal.any([lifetime, request.signal]);
      const isStale = () => signal.aborted || !isCurrent();
      setState(previous => ({ ...previous, busy: true }));
      try {
        const response = await apiClient.get<TelephonyCallSummary[]>(endpoint, { signal });
        if (isStale()) return;
        setState(previous => ({
          ...previous,
          calls: Array.isArray(response) ? response : [],
          error: null,
        }));
      } catch (err) {
        if (isStale()) return;
        if (err instanceof ApiError && err.status === 404) {
          setState(previous => ({ ...previous, unavailable: true, calls: [], error: null }));
        } else {
          const error = err instanceof Error ? err : new Error(String(err));
          setState(previous => ({ ...previous, error }));
          if (!(error instanceof TypeError)) {
            logger.error('Failed to fetch telephony calls', error, {
              component: 'useTelephonyCalls',
            });
          }
        }
      } finally {
        // A superseded request cannot hide the pending current request.
        if (!isStale()) {
          activeRequest.current = null;
          setState(previous => ({ ...previous, busy: false, settled: true }));
        }
      }
    },
    [endpoint, isCurrent, setState, state.unavailable]
  );

  const activeEffect = useRef<{ controller: AbortController; read: typeof fetchCalls } | null>(
    null
  );
  useEffect(() => {
    const controller = new AbortController();
    activeEffect.current = { controller, read: fetchCalls };
    // Strict Mode cancels its probe before external IO, like useApiQuery.
    queueMicrotask(() => {
      void fetchCalls(controller.signal);
    });
    return () => {
      controller.abort();
      activeRequest.current?.abort();
      activeRequest.current = null;
      activeEffect.current = null;
    };
  }, [fetchCalls]);

  const refetch = useCallback(async () => {
    const effect = activeEffect.current;
    if (effect?.read === fetchCalls) await fetchCalls(effect.controller.signal);
  }, [fetchCalls]);

  const active = hasActiveCall(state.calls);
  useEffect(() => {
    if (!scope || state.unavailable || state.busy || !active) return;
    const timer = setTimeout(() => void refetch(), ACTIVE_POLL_MS);
    return () => clearTimeout(timer);
  }, [scope, state, active, refetch]);

  return {
    calls: state.calls,
    hasActiveCall: active,
    isLoading: !!scope && !state.settled,
    isUnavailable: state.unavailable,
    error: state.error,
    refetch,
  };
}
