'use client';

/**
 * The journey player shared by the two brick maps.
 *
 * A pure reducer owns the state — which journey, which step, playing or not —
 * and one effect owns the timer that advances it, cleared as soon as playback
 * stops. Autoplay honours `prefers-reduced-motion`: a reader who asked for less
 * motion steps through a journey by hand.
 */

import { useCallback, useEffect, useMemo, useReducer } from 'react';

import type { FlowView } from './types';

/** How long each step stays lit while a journey plays. */
export const FLOW_STEP_MS = 2400;

export interface PlayerState {
  /** Index of the journey being shown, -1 when none. */
  flow: number;
  step: number;
  playing: boolean;
  /** Steps of the journey being shown (0 when none). */
  length: number;
}

export type PlayerAction =
  | { type: 'select'; flow: number; length: number; autoplay: boolean }
  | { type: 'clear' }
  | { type: 'go'; step: number }
  | { type: 'toggle' }
  | { type: 'tick' };

export const IDLE: PlayerState = { flow: -1, step: 0, playing: false, length: 0 };

export function playerReducer(state: PlayerState, action: PlayerAction): PlayerState {
  switch (action.type) {
    case 'select':
      return { flow: action.flow, step: 0, playing: action.autoplay, length: action.length };
    case 'clear':
      return IDLE;
    case 'go':
      if (state.flow < 0) return state;
      return {
        ...state,
        step: Math.max(0, Math.min(action.step, state.length - 1)),
        playing: false,
      };
    case 'toggle':
      if (state.flow < 0) return state;
      if (state.playing) return { ...state, playing: false };
      // Playing from the last step starts the journey over.
      return { ...state, playing: true, step: state.step >= state.length - 1 ? 0 : state.step };
    case 'tick':
      if (!state.playing) return state;
      if (state.step >= state.length - 1) return { ...state, playing: false };
      return { ...state, step: state.step + 1 };
  }
}

/** Whether the reader asked for less motion — read at the moment of the click. */
function prefersReducedMotion(): boolean {
  return (
    typeof window !== 'undefined' &&
    typeof window.matchMedia === 'function' &&
    window.matchMedia('(prefers-reduced-motion: reduce)').matches
  );
}

export interface FlowPlayer {
  /** The journey being shown, with its current step — null when none. */
  active: { flow: FlowView; step: number } | null;
  index: number;
  step: number;
  playing: boolean;
  /** Show a journey (a second click on the same one closes it). */
  toggleFlow: (index: number) => void;
  /** Show a journey by id and start it — from a replay button or a brick's detail. */
  playById: (id: string) => void;
  togglePlay: () => void;
  goTo: (step: number) => void;
  clear: () => void;
}

export function useFlowPlayer(flows: readonly FlowView[]): FlowPlayer {
  const [state, dispatch] = useReducer(playerReducer, IDLE);

  useEffect(() => {
    if (!state.playing) return;
    const timer = window.setInterval(() => dispatch({ type: 'tick' }), FLOW_STEP_MS);
    return () => window.clearInterval(timer);
  }, [state.playing]);

  const select = useCallback(
    (index: number) =>
      dispatch({
        type: 'select',
        flow: index,
        length: flows[index]?.steps.length ?? 0,
        autoplay: !prefersReducedMotion(),
      }),
    [flows]
  );

  const toggleFlow = useCallback(
    (index: number) => (index === state.flow ? dispatch({ type: 'clear' }) : select(index)),
    [select, state.flow]
  );

  const playById = useCallback(
    (id: string) => {
      const index = flows.findIndex(f => f.id === id);
      if (index >= 0) select(index);
    },
    [flows, select]
  );

  const togglePlay = useCallback(() => dispatch({ type: 'toggle' }), []);
  const goTo = useCallback((step: number) => dispatch({ type: 'go', step }), []);
  const clear = useCallback(() => dispatch({ type: 'clear' }), []);

  const flow = state.flow >= 0 ? flows[state.flow] : undefined;
  const active = useMemo(() => (flow ? { flow, step: state.step } : null), [flow, state.step]);

  return {
    active,
    index: state.flow,
    step: state.step,
    playing: state.playing,
    toggleFlow,
    playById,
    togglePlay,
    goTo,
    clear,
  };
}
