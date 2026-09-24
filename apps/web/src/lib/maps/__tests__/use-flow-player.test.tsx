/**
 * The journey player: a pure reducer, and a hook whose timer stops with it.
 */

import { act, renderHook } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { FLOW_STEP_MS, IDLE, playerReducer, useFlowPlayer } from '../use-flow-player';
import type { FlowView } from '../types';

const flows: FlowView[] = [
  {
    id: 'a',
    name: 'A',
    summary: 's',
    icon: 'send',
    steps: [
      { brick: 'f.1', text: '1' },
      { brick: 'f.2', text: '2' },
      { brick: 'f.3', text: '3' },
    ],
  },
  { id: 'b', name: 'B', summary: 's', icon: 'send', steps: [{ brick: 'f.1', text: '1' }] },
];

describe('playerReducer', () => {
  it('selects, steps within bounds, plays and pauses', () => {
    let state = playerReducer(IDLE, { type: 'select', flow: 0, length: 3, autoplay: false });
    expect(state).toEqual({ flow: 0, step: 0, playing: false, length: 3 });
    state = playerReducer(state, { type: 'go', step: 9 });
    expect(state.step).toBe(2);
    state = playerReducer(state, { type: 'go', step: -4 });
    expect(state.step).toBe(0);
    state = playerReducer(state, { type: 'toggle' });
    expect(state.playing).toBe(true);
    state = playerReducer(state, { type: 'toggle' });
    expect(state.playing).toBe(false);
  });

  it('starts over when played from the last step, and stops at the end', () => {
    let state = playerReducer(IDLE, { type: 'select', flow: 0, length: 3, autoplay: false });
    state = playerReducer(state, { type: 'go', step: 2 });
    state = playerReducer(state, { type: 'toggle' });
    expect(state).toMatchObject({ step: 0, playing: true });
    state = playerReducer(state, { type: 'tick' });
    state = playerReducer(state, { type: 'tick' });
    expect(state).toMatchObject({ step: 2, playing: true });
    state = playerReducer(state, { type: 'tick' });
    expect(state).toMatchObject({ step: 2, playing: false });
    expect(playerReducer(state, { type: 'tick' })).toBe(state);
  });

  it('does nothing without a journey, and clears back to idle', () => {
    expect(playerReducer(IDLE, { type: 'go', step: 1 })).toBe(IDLE);
    expect(playerReducer(IDLE, { type: 'toggle' })).toBe(IDLE);
    const state = playerReducer(IDLE, { type: 'select', flow: 1, length: 1, autoplay: true });
    expect(playerReducer(state, { type: 'clear' })).toBe(IDLE);
  });
});

describe('useFlowPlayer', () => {
  let reduced = false;
  beforeEach(() => {
    vi.useFakeTimers();
    reduced = false;
    vi.stubGlobal(
      'matchMedia',
      vi.fn(() => ({ matches: reduced, addEventListener: vi.fn(), removeEventListener: vi.fn() }))
    );
  });
  afterEach(() => {
    vi.useRealTimers();
    vi.unstubAllGlobals();
  });

  it('plays a journey step by step and stops at its end', () => {
    const { result } = renderHook(() => useFlowPlayer(flows));
    act(() => result.current.toggleFlow(0));
    expect(result.current.active?.flow.id).toBe('a');
    expect(result.current.playing).toBe(true);
    act(() => vi.advanceTimersByTime(FLOW_STEP_MS));
    expect(result.current.step).toBe(1);
    act(() => vi.advanceTimersByTime(FLOW_STEP_MS * 3));
    expect(result.current).toMatchObject({ step: 2, playing: false });
  });

  it('never autoplays for a reader who asked for less motion', () => {
    reduced = true;
    const { result } = renderHook(() => useFlowPlayer(flows));
    act(() => result.current.playById('a'));
    expect(result.current.playing).toBe(false);
    act(() => vi.advanceTimersByTime(FLOW_STEP_MS * 2));
    expect(result.current.step).toBe(0);
  });

  it('closes a journey clicked twice, ignores an unknown id, and clears', () => {
    const { result } = renderHook(() => useFlowPlayer(flows));
    act(() => result.current.toggleFlow(1));
    act(() => result.current.toggleFlow(1));
    expect(result.current.active).toBeNull();
    act(() => result.current.playById('nope'));
    expect(result.current.active).toBeNull();
    act(() => result.current.playById('b'));
    act(() => result.current.goTo(0));
    act(() => result.current.togglePlay());
    act(() => result.current.clear());
    expect(result.current.index).toBe(-1);
  });
});
