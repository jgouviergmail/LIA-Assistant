/**
 * Timer-driven looped timeline — the single animation driver of the /more
 * scenes.
 *
 * Deliberately built on setTimeout (never animationend/transitionend, which
 * jsdom does not deliver): a scene declares its phases as steps at millisecond
 * offsets and switches CSS classes on the returned state; the browser's CSS
 * transitions do the easing.
 *
 * Contract:
 * - steps apply at their offsets from cycle start; after the last step plus
 *   `restMs`, the cycle restarts from steps[0];
 * - `active: false` freezes the current state and clears every timer (used
 *   for out-of-viewport cards and the WCAG 2.2.2 pause control);
 * - under prefers-reduced-motion the hook returns the last step's state (the
 *   scene's designed resting frame) and never schedules a timer;
 * - unmount clears every timer.
 */

'use client';

import { useEffect, useRef, useState, useSyncExternalStore } from 'react';

export interface TimelineStep<S> {
  /** Milliseconds from cycle start. steps[0] must be at 0 (initial frame). */
  at: number;
  state: S;
}

const REDUCED_MOTION_QUERY = '(prefers-reduced-motion: reduce)';

function subscribeToReducedMotion(onChange: () => void): () => void {
  const mql = window.matchMedia(REDUCED_MOTION_QUERY);
  mql.addEventListener('change', onChange);
  return () => mql.removeEventListener('change', onChange);
}

function getReducedMotionSnapshot(): boolean {
  return window.matchMedia(REDUCED_MOTION_QUERY).matches;
}

function getReducedMotionServerSnapshot(): boolean {
  return false;
}

/**
 * Live media-query subscription via useSyncExternalStore (the codebase's
 * sanctioned pattern for external state in new files — no setState-in-effect):
 * SSR renders the animated markup (snapshot false), the client snapshot takes
 * over at hydration, and later OS-level preference flips propagate live.
 */
function usePrefersReducedMotion(): boolean {
  return useSyncExternalStore(
    subscribeToReducedMotion,
    getReducedMotionSnapshot,
    getReducedMotionServerSnapshot
  );
}

export function useLoopedTimeline<S>(
  steps: readonly TimelineStep<S>[],
  { active, restMs = 2500 }: { active: boolean; restMs?: number }
): S {
  // Scenes declare steps as module-level constants; keep a ref so an inline
  // array literal cannot retrigger the scheduling effect on every render.
  // Synced in an effect (never during render — react-hooks/refs).
  const stepsRef = useRef(steps);
  useEffect(() => {
    stepsRef.current = steps;
  });

  const [state, setState] = useState<S>(steps[0].state);
  const reduced = usePrefersReducedMotion();

  useEffect(() => {
    if (reduced || !active) return undefined;

    // Single-timer chain: each firing applies its step synchronously and
    // schedules the next transition. This keeps exactly one pending timer
    // (trivial cleanup) and avoids a 0 ms restart timer sitting on the cycle
    // boundary, which fake-timer runners may defer past an exact-boundary
    // advance.
    let timer: ReturnType<typeof setTimeout> | undefined;
    const run = (idx: number) => {
      const current = stepsRef.current;
      setState(current[idx].state);
      const nextIdx = (idx + 1) % current.length;
      const delay = nextIdx === 0 ? restMs : current[nextIdx].at - current[idx].at;
      timer = setTimeout(() => run(nextIdx), delay);
    };
    run(0);

    return () => clearTimeout(timer);
  }, [active, reduced, restMs]);

  return reduced ? steps[steps.length - 1].state : state;
}
