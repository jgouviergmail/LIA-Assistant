/**
 * Mission controller: pacing, bounded funnel events, focus intent.
 *
 * The reducer stays pure; this hook owns the impure edges:
 * - timers pace reading/planning ONLY when motion is allowed (`paced`);
 * - the injected `onEvent` callback receives the bounded per-run funnel with
 *   at-most-once semantics per started run (client attempts, never delivery).
 *   Start and completion emit BOTH the aggregate event and the bounded
 *   per-mission variant (which mission engages / converts).
 *
 * Concurrency design: `send()` is the single mutation point. It previews the
 * pure reducer against `pendingRef` IN EVENT PHASE (handlers/timers — never
 * during render, per the react-hooks/refs rule), so a rejected or duplicate
 * event can never emit a phantom funnel attempt, even under a double-click
 * that outruns React's async re-render. The real `dispatch` then applies the
 * SAME event sequence, so `pendingRef` and the committed state converge by
 * reducer determinism.
 *
 * No fetch/telemetry here: the caller wires the real emitter, tests inject a
 * spy, and the mission never depends on either. `demo_viewed` is page-level
 * and lives in GuidedShowroom (one attempt per page, not per mission).
 */

import { useCallback, useEffect, useMemo, useReducer, useRef } from 'react';

import { initialStateFor, makeShowroomReducer } from '@/components/showroom/reducer';
import type {
  ShowroomDecisionKind,
  ShowroomEvent,
  ShowroomMissionDefinition,
  ShowroomState,
} from '@/components/showroom/types';
import type { ShowroomFunnelEvent } from '@/lib/product-telemetry';

// Re-exported so mission consumers keep a single import site.
export type { ShowroomFunnelEvent };

export type ShowroomCtaKind = 'source' | 'release' | 'install_guide';

const CTA_EVENTS: Record<ShowroomCtaKind, ShowroomFunnelEvent> = {
  source: 'demo_source_clicked',
  release: 'demo_release_clicked',
  install_guide: 'demo_install_guide_clicked',
};

/** Demonstration pacing (ms) — a storyboard rhythm, not live inference. */
export const SHOWROOM_PACING_MS = {
  sourceReveal: 900,
  toPlanning: 1100,
  toDecision: 1600,
} as const;

/** Total pacing budget — used to display a deterministic trace duration. */
export function missionTraceDurationMs(
  def: Pick<ShowroomMissionDefinition, 'sources'>
): number {
  return (
    SHOWROOM_PACING_MS.sourceReveal * def.sources.length +
    SHOWROOM_PACING_MS.toPlanning +
    SHOWROOM_PACING_MS.toDecision
  );
}

export interface UseShowroomMissionOptions {
  /** The immutable mission definition (stable per mounted mission). */
  def: ShowroomMissionDefinition;
  /** False under prefers-reduced-motion: explicit Continue buttons instead. */
  paced: boolean;
  /** Bounded funnel sink (fire-and-forget attempts). Optional by contract. */
  onEvent?: (event: ShowroomFunnelEvent) => void;
}

export interface ShowroomMissionHandle {
  state: ShowroomState;
  start: () => void;
  advance: () => void;
  decide: (index: number, decision: ShowroomDecisionKind) => void;
  restart: () => void;
  markProofOpened: () => void;
  markCta: (kind: ShowroomCtaKind) => void;
}

export function useShowroomMission({
  def,
  paced,
  onEvent,
}: UseShowroomMissionOptions): ShowroomMissionHandle {
  // `def` is immutable and stable for a mounted mission (the picker remounts
  // by key on change), so the reducer identity is stable too.
  const reducer = useMemo(() => makeShowroomReducer(def), [def]);
  const [state, dispatch] = useReducer(reducer, def, initialStateFor);
  /** Event-phase view of the state — only `send()` may write it. */
  const pendingRef = useRef<ShowroomState>(initialStateFor(def));
  /** At-most-once guards for the current run (reset on START). */
  const firedRef = useRef<Set<string>>(new Set());

  const emitOnce = useCallback(
    (guard: string, event: ShowroomFunnelEvent) => {
      if (firedRef.current.has(guard)) return;
      firedRef.current.add(guard);
      onEvent?.(event);
    },
    [onEvent]
  );

  /** Apply an event; returns the next state, or null when it was ignored. */
  const send = useCallback(
    (event: ShowroomEvent): ShowroomState | null => {
      const current = pendingRef.current;
      const next = reducer(current, event);
      if (next === current) return null;
      pendingRef.current = next;
      dispatch(event);
      return next;
    },
    [reducer]
  );

  const start = useCallback(() => {
    if (pendingRef.current.phase !== 'ready') return;
    firedRef.current = new Set();
    if (send({ type: 'START' }) !== null) {
      onEvent?.('demo_mission_started');
      onEvent?.(`demo_mission_started_${def.id}`);
    }
  }, [def.id, onEvent, send]);

  const advance = useCallback(() => {
    send({ type: 'ADVANCE' });
  }, [send]);

  const decide = useCallback(
    (index: number, decision: ShowroomDecisionKind) => {
      const next = send({ type: 'DECIDE', index, decision });
      if (next === null) return; // rejected/out-of-order: no phantom event
      onEvent?.(`demo_hitl_${decision}`);
      emitOnce('first_hitl', 'demo_first_hitl_decided');
      if (next.phase === 'receipt') {
        emitOnce('completed', 'demo_completed');
        emitOnce('completed_mission', `demo_completed_${def.id}`);
      }
    },
    [def.id, emitOnce, onEvent, send]
  );

  const restart = useCallback(() => {
    send({ type: 'RESTART' });
  }, [send]);

  const markProofOpened = useCallback(() => {
    if (pendingRef.current.phase !== 'receipt') return;
    emitOnce('proof', 'demo_first_proof_opened');
  }, [emitOnce]);

  const markCta = useCallback(
    (kind: ShowroomCtaKind) => {
      if (pendingRef.current.phase !== 'receipt') return;
      emitOnce(`cta:${kind}`, CTA_EVENTS[kind]);
    },
    [emitOnce]
  );

  // Demonstration pacing: one bounded timer per auto-advancing step.
  useEffect(() => {
    if (!paced) return undefined;
    let delay: number | null = null;
    if (state.phase === 'reading_sources') {
      delay =
        state.sourcesRead < def.sources.length
          ? SHOWROOM_PACING_MS.sourceReveal
          : SHOWROOM_PACING_MS.toPlanning;
    } else if (state.phase === 'planning') {
      delay = SHOWROOM_PACING_MS.toDecision;
    }
    if (delay === null) return undefined;
    const timer = setTimeout(() => send({ type: 'ADVANCE' }), delay);
    return () => clearTimeout(timer);
  }, [def.sources.length, paced, send, state.phase, state.sourcesRead]);

  return { state, start, advance, decide, restart, markProofOpened, markCta };
}
