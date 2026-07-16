import { useCallback, useEffect, useMemo, useRef } from 'react';

/**
 * Staleness guard for polling / re-fetching hooks (audit F037).
 *
 * Centralises the "only the latest request, while still mounted, may touch
 * state" rule that every polling hook needs. Without it, an out-of-order or
 * post-unmount response silently overwrites fresher state (a stale poll clobbers
 * the current value, or React warns about setting state on an unmounted tree).
 *
 * Usage:
 * ```ts
 * const guard = useStaleGuard();
 * const fetchThing = useCallback(async () => {
 *   const isStale = guard.begin();          // claim a monotonic request id
 *   const data = await fetch(...);
 *   if (isStale()) return;                  // a newer request superseded us
 *   setThing(data);
 * } finally {
 *   if (!isStale()) setLoading(false);      // NOT isMounted() — see below
 * }, [guard]);
 * ```
 *
 * IMPORTANT (audit F037): the `finally`/loading path must be gated by the
 * request-scoped `!isStale()`, NOT by `isMounted()`. If an OLDER request finishes
 * while a NEWER one is still in flight, an `isMounted()`-gated finally would clear
 * `loading` prematurely and hide the pending fresh request. `isStale()` returns
 * `true` for the superseded request, so only the current one clears loading.
 * `isMounted()` remains useful only for effects with no competing request.
 *
 * Invalidate the in-flight request when inputs change (e.g. the user becomes
 * `null`) by simply calling `begin()` again — the previous `isStale()` will then
 * report `true`.
 */
export interface StaleGuard {
  /**
   * Start a new request and return an `isStale()` predicate scoped to it.
   * The predicate is `true` once a newer request has started or the component
   * has unmounted — callers must check it before every state mutation.
   */
  begin: () => () => boolean;
  /** Whether the owning component is still mounted. */
  isMounted: () => boolean;
}

export function useStaleGuard(): StaleGuard {
  const mountedRef = useRef(true);
  const requestIdRef = useRef(0);

  useEffect(() => {
    mountedRef.current = true;
    return () => {
      mountedRef.current = false;
    };
  }, []);

  const begin = useCallback((): (() => boolean) => {
    const requestId = ++requestIdRef.current;
    return () => !mountedRef.current || requestId !== requestIdRef.current;
  }, []);

  const isMounted = useCallback(() => mountedRef.current, []);

  // Stable object so callers can list `guard` directly in effect/callback deps.
  return useMemo(() => ({ begin, isMounted }), [begin, isMounted]);
}
