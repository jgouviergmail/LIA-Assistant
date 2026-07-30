'use client';

/**
 * Shared scroll plumbing for the LIA Cosmos identity (spec 2026-07-30).
 *
 * One passive, rAF-throttled scroll/resize subscription per consumer, plus the
 * two pure helpers every cosmos choreography derives its progress from. Kept
 * deliberately tiny: primitives subscribe individually (a handful per page),
 * each doing transform-only writes in its callback.
 */

import { useCallback, useEffect, useRef, useSyncExternalStore } from 'react';

/** Clamps a number to the [0, 1] interval. */
export function clamp01(value: number): number {
  return Math.min(1, Math.max(0, value));
}

/**
 * Progress of a section through the viewport: 0 while its top edge is still
 * below the fold, 1 once its bottom edge has left through the top.
 */
export function sectionProgress(
  rect: { top: number; height: number },
  viewportHeight: number
): number {
  return clamp01((viewportHeight - rect.top) / (viewportHeight + rect.height));
}

/** Live check — evaluated per frame so OS-level toggles apply immediately. */
export function prefersReducedMotion(): boolean {
  return (
    typeof window !== 'undefined' &&
    window.matchMedia('(prefers-reduced-motion: reduce)').matches
  );
}

/**
 * Reactive media-query flag, hydration-safe (server snapshot: false) and
 * setState-free — the repo's convention for new stateful hooks
 * (useSyncExternalStore, never setState-in-effect).
 */
export function useMediaFlag(query: string): boolean {
  const subscribe = useCallback(
    (onChange: () => void) => {
      const mq = window.matchMedia(query);
      mq.addEventListener?.('change', onChange);
      return () => mq.removeEventListener?.('change', onChange);
    },
    [query]
  );
  return useSyncExternalStore(
    subscribe,
    () => window.matchMedia(query).matches,
    () => false
  );
}

/**
 * Subscribes `callback` to scroll + resize, rAF-throttled, fired once on
 * mount. The callback ref is refreshed every render so consumers can close
 * over current props/state without re-subscribing.
 */
export function useCosmosScroll(callback: (scrollY: number) => void): void {
  const callbackRef = useRef(callback);
  // Latest-ref pattern: refreshed in an effect (never during render — the
  // react-hooks rule the pre-commit lint enforces repo-wide).
  useEffect(() => {
    callbackRef.current = callback;
  });

  useEffect(() => {
    let ticking = false;
    let frame = 0;

    const run = () => {
      ticking = false;
      callbackRef.current(window.scrollY);
    };
    const schedule = () => {
      if (ticking) return;
      ticking = true;
      frame = requestAnimationFrame(run);
    };

    window.addEventListener('scroll', schedule, { passive: true });
    window.addEventListener('resize', schedule);
    schedule();

    return () => {
      window.removeEventListener('scroll', schedule);
      window.removeEventListener('resize', schedule);
      cancelAnimationFrame(frame);
    };
  }, []);
}
