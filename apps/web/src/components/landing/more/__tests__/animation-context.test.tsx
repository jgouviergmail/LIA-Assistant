/**
 * MoreAnimationContext + AnimationPauseToggle — the WCAG 2.2.2 mechanism of
 * the /more page: the looping scenes auto-start and collectively exceed 5 s,
 * so the page must offer a visible pause control (prefers-reduced-motion is a
 * preference, not an in-page mechanism).
 *
 * Contract under test:
 *  - native button with a stable translated name and aria-pressed reflecting
 *    the paused state;
 *  - pausing stops timer advancement for scenes driven through the context
 *    (integration with useLoopedTimeline) and resuming restarts them;
 *  - keyboard activation (Enter) works — native button semantics.
 */

import { act, fireEvent, render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import {
  AnimationPauseToggle,
  MoreAnimationProvider,
  useMoreAnimation,
} from '../animation-context';
import { useLoopedTimeline, type TimelineStep } from '../useLoopedTimeline';

const STEPS: readonly TimelineStep<string>[] = [
  { at: 0, state: 'start' },
  { at: 200, state: 'end' },
];

function ProbeScene() {
  const { playing } = useMoreAnimation();
  const s = useLoopedTimeline(STEPS, { active: playing, restMs: 400 });
  return <div data-testid="scene">{s}</div>;
}

const TOGGLE_NAME = 'more.controls.pause_animations';

describe('MoreAnimationProvider + AnimationPauseToggle', () => {
  beforeEach(() => vi.useFakeTimers());
  afterEach(() => {
    vi.useRealTimers();
    vi.restoreAllMocks();
  });

  function setup() {
    render(
      <MoreAnimationProvider>
        <AnimationPauseToggle />
        <ProbeScene />
      </MoreAnimationProvider>
    );
    return screen.getByRole('button', { name: TOGGLE_NAME });
  }

  it('renders a native button, unpressed while playing', () => {
    const button = setup();
    expect(button).toHaveAttribute('aria-pressed', 'false');
  });

  it('pausing freezes the scenes and clears their timers; resuming restarts', () => {
    // fireEvent.click (synchronous) rather than userEvent: userEvent v14
    // deadlocks under fake timers even with advanceTimers/delay:null, and a
    // native button's click is the exact browser contract being exercised.
    const button = setup();

    act(() => vi.advanceTimersByTime(200));
    expect(screen.getByTestId('scene').textContent).toBe('end');

    fireEvent.click(button);
    expect(button).toHaveAttribute('aria-pressed', 'true');
    expect(vi.getTimerCount()).toBe(0);

    act(() => vi.advanceTimersByTime(10_000));
    expect(screen.getByTestId('scene').textContent).toBe('end');

    fireEvent.click(button);
    expect(button).toHaveAttribute('aria-pressed', 'false');
    expect(screen.getByTestId('scene').textContent).toBe('start');
  });

  it('activates from the keyboard (native button, Enter)', async () => {
    // Real timers here: this test asserts keyboard semantics only, and
    // userEvent (which does implement Enter→click on native buttons, unlike
    // fireEvent) runs on real timers.
    vi.useRealTimers();
    const user = userEvent.setup();
    const button = setup();

    act(() => button.focus());
    await user.keyboard('{Enter}');
    expect(button).toHaveAttribute('aria-pressed', 'true');
  });

  it('defaults to playing outside a provider (scenes never dead on a wiring miss)', () => {
    render(<ProbeScene />);
    act(() => vi.advanceTimersByTime(200));
    expect(screen.getByTestId('scene').textContent).toBe('end');
  });
});
