'use client';

/**
 * Timeline engine of the animated conversation mockup.
 *
 * Extracted from the historical ChatMockup (UX P12). Since the hero
 * transplant, `InteractiveChatMockup` is the single consumer — the landing
 * hero (CTA hidden) and the /demo page (CTA shown) both mount it: the
 * historical auto loop runs until the visitor interacts, then scene
 * selection, pause/resume and replay take over.
 *
 * Interaction model (interactive mode):
 *  - `select`/`replay` switch to MANUAL mode: the act plays once and freezes
 *    on its resolution frame (paused) instead of cross-fading onward.
 *  - `togglePause` pauses/resumes the running schedule; resuming a manual act
 *    that already ended replays it from the top.
 *  - Under `prefers-reduced-motion`, nothing is ever scheduled: selection
 *    swaps static resolution frames (every step kind reached at once closes
 *    the typing/backstage/stream windows by construction of the acts).
 */

import { useCallback, useEffect, useRef, useState, useSyncExternalStore } from 'react';

import { REDUCED_MOTION_KINDS, SCENARIOS, type Scenario, type ScenarioId } from './scenarios';

/** Cross-fade duration between two acts of the auto loop. */
export const CYCLE_FADE_MS = 600;

const REDUCED_MOTION_QUERY = '(prefers-reduced-motion: reduce)';

function subscribeReducedMotion(onChange: () => void): () => void {
  const mql = window.matchMedia(REDUCED_MOTION_QUERY);
  mql.addEventListener('change', onChange);
  return () => mql.removeEventListener('change', onChange);
}

/**
 * SSR-safe reduced-motion signal: the server snapshot is `false` (animate by
 * default), the client snapshot re-renders after hydration without a
 * mismatch, and a live preference flip is tracked.
 */
function useReducedMotion(): boolean {
  return useSyncExternalStore(
    subscribeReducedMotion,
    () => window.matchMedia(REDUCED_MOTION_QUERY).matches,
    () => false
  );
}

interface EngineCallbacks {
  setScenarioIndex: (index: number) => void;
  setStepCount: (count: number) => void;
  setFading: (fading: boolean) => void;
  setPaused: (paused: boolean) => void;
}

interface TimelineEngine {
  start: () => void;
  select: (id: ScenarioId) => void;
  replay: () => void;
  togglePause: () => void;
  dispose: () => void;
}

/**
 * Plain closure factory (module level, hook-free) so every scheduling branch
 * stays out of the component render path. All state the schedule needs to
 * survive pause/resume lives here; React state only mirrors what renders.
 */
function createTimelineEngine(cb: EngineCallbacks): TimelineEngine {
  let timers: ReturnType<typeof setTimeout>[] = [];
  let mode: 'auto' | 'manual' = 'auto';
  let index = 0;
  /** Epoch ms when the current run started (valid while unpaused). */
  let actStart = 0;
  /** Ms of the act already consumed before the current run. */
  let elapsed = 0;
  let paused = false;

  const clearTimers = (): void => {
    timers.forEach(clearTimeout);
    timers = [];
  };

  /** (Re)start act `nextIndex` from `fromMs` into its schedule. */
  const runAct = (nextIndex: number, fromMs: number): void => {
    clearTimers();
    const scenario = SCENARIOS[nextIndex];
    index = nextIndex;
    actStart = Date.now();
    elapsed = fromMs;
    paused = false;
    cb.setPaused(false);
    cb.setScenarioIndex(nextIndex);
    cb.setFading(false);
    cb.setStepCount(scenario.steps.filter(step => step.at <= fromMs).length);

    scenario.steps.forEach((step, i) => {
      if (step.at > fromMs) {
        timers.push(setTimeout(() => cb.setStepCount(i + 1), step.at - fromMs));
      }
    });

    if (mode === 'auto') {
      timers.push(
        setTimeout(() => cb.setFading(true), Math.max(0, scenario.holdMs - fromMs)),
        setTimeout(
          () => runAct((nextIndex + 1) % SCENARIOS.length, 0),
          Math.max(0, scenario.holdMs + CYCLE_FADE_MS - fromMs)
        )
      );
    } else {
      // Manual: play to the end of the act, then freeze on the resolution
      // frame — no fade, no advance. Resuming from there replays.
      timers.push(
        setTimeout(
          () => {
            clearTimers();
            elapsed = scenario.holdMs;
            paused = true;
            cb.setPaused(true);
          },
          Math.max(0, scenario.holdMs - fromMs)
        )
      );
    }
  };

  const pause = (): void => {
    if (paused) return;
    clearTimers();
    elapsed += Date.now() - actStart;
    paused = true;
    cb.setPaused(true);
  };

  const resume = (): void => {
    if (!paused) return;
    // A manual act frozen on its final frame replays from the top.
    const fromMs = mode === 'manual' && elapsed >= SCENARIOS[index].holdMs ? 0 : elapsed;
    runAct(index, fromMs);
  };

  return {
    start: () => runAct(0, 0),
    select: (id: ScenarioId) => {
      mode = 'manual';
      runAct(
        SCENARIOS.findIndex(scenario => scenario.id === id),
        0
      );
    },
    replay: () => {
      mode = 'manual';
      runAct(index, 0);
    },
    togglePause: () => (paused ? resume() : pause()),
    dispose: clearTimers,
  };
}

export interface MockupTimelineControls {
  /** Jump to a scene and play it once (manual mode: no auto-advance). */
  select: (id: ScenarioId) => void;
  /** Restart the current scene from its first beat (manual mode). */
  replay: () => void;
  /** Pause/resume; resuming a manual scene that ended replays it. */
  togglePause: () => void;
  paused: boolean;
  /** Step-reveal progress through the current scene, 0..1. */
  progress: number;
}

export interface MockupTimeline {
  scenario: Scenario;
  reached: (kind: string) => boolean;
  fading: boolean;
  reducedMotion: boolean;
  controls: MockupTimelineControls;
}

/** Timeline hook: reveals scenario steps on schedule, then cycles. */
export function useMockupTimeline(options: { interactive?: boolean } = {}): MockupTimeline {
  const { interactive = false } = options;
  const [scenarioIndex, setScenarioIndex] = useState(0);
  const [stepCount, setStepCount] = useState(0);
  const [fading, setFading] = useState(false);
  const [paused, setPaused] = useState(false);
  const reducedMotion = useReducedMotion();
  const engineRef = useRef<TimelineEngine | null>(null);

  useEffect(() => {
    if (reducedMotion) return;
    const engine = createTimelineEngine({ setScenarioIndex, setStepCount, setFading, setPaused });
    engineRef.current = engine;
    engine.start();
    return () => {
      engineRef.current = null;
      engine.dispose();
    };
  }, [reducedMotion]);

  // Under reduced motion the engine never exists: selection swaps static
  // resolution frames directly.
  const select = useCallback(
    (id: ScenarioId) => {
      if (engineRef.current) {
        engineRef.current.select(id);
        return;
      }
      setScenarioIndex(SCENARIOS.findIndex(scenario => scenario.id === id));
    },
    [setScenarioIndex]
  );
  const replay = useCallback(() => engineRef.current?.replay(), []);
  const togglePause = useCallback(() => engineRef.current?.togglePause(), []);

  const scenario = SCENARIOS[scenarioIndex];
  const visible = new Set(scenario.steps.slice(0, stepCount).map(step => step.kind));
  const reached = reducedMotion
    ? interactive
      ? () => true
      : (kind: string) => REDUCED_MOTION_KINDS.has(kind)
    : (kind: string) => visible.has(kind);

  return {
    scenario,
    reached,
    // Derived, not reset in an effect: a live flip to reduced motion while a
    // cross-fade was mid-flight must not freeze the static frame invisible.
    fading: fading && !reducedMotion,
    reducedMotion,
    controls: {
      select,
      replay,
      togglePause,
      paused,
      progress: reducedMotion ? 1 : stepCount / scenario.steps.length,
    },
  };
}
