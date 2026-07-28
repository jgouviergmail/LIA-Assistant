/**
 * useLoopedTimeline — the single animation driver of the /more scenes.
 *
 * Contract under test (spec, animation system):
 *  - steps apply at their offsets, and the cycle loops after last step + rest;
 *  - active=false freezes the current state and clears every timer;
 *  - prefers-reduced-motion renders the resting frame (last step) and never
 *    schedules a timer;
 *  - unmount clears every timer (no leaks between cards).
 *
 * Timer-driven on purpose: animationend/transitionend never fire in jsdom.
 */

import { act, render, screen } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { useLoopedTimeline, type TimelineStep } from '../useLoopedTimeline';

const STEPS: readonly TimelineStep<string>[] = [
  { at: 0, state: 'a' },
  { at: 100, state: 'b' },
  { at: 300, state: 'c' },
];

function Probe({ active }: { active: boolean }) {
  const s = useLoopedTimeline(STEPS, { active, restMs: 500 });
  return <div data-testid="s">{s}</div>;
}

function mockReducedMotion(matches: boolean) {
  vi.spyOn(window, 'matchMedia').mockImplementation(
    (query: string) =>
      ({
        matches: query.includes('prefers-reduced-motion') ? matches : false,
        media: query,
        addEventListener: vi.fn(),
        removeEventListener: vi.fn(),
        addListener: vi.fn(),
        removeListener: vi.fn(),
        onchange: null,
        dispatchEvent: vi.fn(),
      }) as MediaQueryList
  );
}

describe('useLoopedTimeline', () => {
  beforeEach(() => {
    vi.useFakeTimers();
    mockReducedMotion(false);
  });

  afterEach(() => {
    vi.useRealTimers();
    vi.restoreAllMocks();
  });

  it('applies steps at their offsets and loops after the rest pause', () => {
    render(<Probe active />);
    expect(screen.getByTestId('s').textContent).toBe('a');

    act(() => vi.advanceTimersByTime(100));
    expect(screen.getByTestId('s').textContent).toBe('b');

    act(() => vi.advanceTimersByTime(200));
    expect(screen.getByTestId('s').textContent).toBe('c');

    // last step (300) + rest (500) => cycle restarts at step 0.
    act(() => vi.advanceTimersByTime(500));
    expect(screen.getByTestId('s').textContent).toBe('a');

    // And the second cycle advances normally.
    act(() => vi.advanceTimersByTime(100));
    expect(screen.getByTestId('s').textContent).toBe('b');
  });

  it('freezes the current state and clears every timer when active drops', () => {
    const { rerender } = render(<Probe active />);
    act(() => vi.advanceTimersByTime(100));
    expect(screen.getByTestId('s').textContent).toBe('b');

    rerender(<Probe active={false} />);
    expect(vi.getTimerCount()).toBe(0);

    act(() => vi.advanceTimersByTime(10_000));
    expect(screen.getByTestId('s').textContent).toBe('b');
  });

  it('resumes cycling from the start when active comes back', () => {
    const { rerender } = render(<Probe active={false} />);
    expect(vi.getTimerCount()).toBe(0);

    rerender(<Probe active />);
    act(() => vi.advanceTimersByTime(300));
    expect(screen.getByTestId('s').textContent).toBe('c');
  });

  it('renders the resting frame and schedules nothing under reduced motion', () => {
    mockReducedMotion(true);
    render(<Probe active />);
    expect(screen.getByTestId('s').textContent).toBe('c');
    expect(vi.getTimerCount()).toBe(0);
  });

  it('clears every timer on unmount', () => {
    const { unmount } = render(<Probe active />);
    act(() => vi.advanceTimersByTime(150));
    expect(vi.getTimerCount()).toBeGreaterThan(0);

    unmount();
    expect(vi.getTimerCount()).toBe(0);
  });
});
