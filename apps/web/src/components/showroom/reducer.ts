/**
 * Pure, deterministic reducer for the multi-mission guided showroom.
 *
 * Contract (mirrors the chat-reducer doctrine): no side effects, no timers,
 * no Date, no i18n, no telemetry — the controller hook owns pacing and event
 * emission. Every ignored event returns the SAME state reference so React
 * consumers never re-render on a no-op.
 *
 * The reducer is a factory: mission bounds (source count, decision sequence,
 * allowed kinds per step) come from the immutable definition, so the machine
 * itself stays mission-agnostic and every mission gets the same guarantees.
 */

import type {
  ShowroomEvent,
  ShowroomMissionDefinition,
  ShowroomState,
} from '@/components/showroom/types';

/** Fresh pre-run state for a mission (one null slot per decision). */
export function initialStateFor(
  def: Pick<ShowroomMissionDefinition, 'decisions'>
): ShowroomState {
  return {
    phase: 'ready',
    runId: 0,
    sourcesRead: 0,
    decisionIndex: 0,
    decisions: def.decisions.map(() => null),
  };
}

/** Build the mission's pure reducer; unknown/out-of-order events are identity. */
export function makeShowroomReducer(
  def: Pick<ShowroomMissionDefinition, 'sources' | 'decisions'>
): (state: ShowroomState, event: ShowroomEvent) => ShowroomState {
  const sourceCount = def.sources.length;

  return function showroomReducer(
    state: ShowroomState,
    event: ShowroomEvent
  ): ShowroomState {
    switch (event.type) {
      case 'START':
        if (state.phase !== 'ready') return state;
        return {
          ...initialStateFor(def),
          phase: 'reading_sources',
          runId: state.runId + 1,
        };

      case 'ADVANCE':
        if (state.phase === 'reading_sources') {
          if (state.sourcesRead < sourceCount) {
            return { ...state, sourcesRead: state.sourcesRead + 1 };
          }
          return { ...state, phase: 'planning' };
        }
        if (state.phase === 'planning') {
          return { ...state, phase: 'decision', decisionIndex: 0 };
        }
        // ready / decision / receipt: ADVANCE never skips a decision.
        return state;

      case 'DECIDE': {
        if (state.phase !== 'decision') return state;
        if (event.index !== state.decisionIndex) return state;
        const spec = def.decisions[event.index];
        if (!spec || !spec.allowed.includes(event.decision)) return state;
        const decisions = state.decisions.map((d, i) =>
          i === event.index ? event.decision : d
        );
        if (event.index === def.decisions.length - 1) {
          return { ...state, phase: 'receipt', decisions };
        }
        return { ...state, decisions, decisionIndex: state.decisionIndex + 1 };
      }

      case 'RESTART':
        if (state.phase === 'ready') return state;
        // Keep runId: the NEXT explicit START increments it (per-run events).
        return { ...initialStateFor(def), runId: state.runId };

      default:
        return state;
    }
  };
}
