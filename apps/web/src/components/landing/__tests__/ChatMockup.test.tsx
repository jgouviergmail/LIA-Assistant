/**
 * ChatMockup — timeline progression, backstage window, stream chrome and the
 * reduced-motion static frame. The global i18n mock echoes keys, so
 * assertions target key strings; timers are faked and advanced manually.
 */

import { act, render, screen } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { ChatMockup } from '../ChatMockup';
import { SCENARIOS } from '../mockup/scenarios';

const TK = 'landing.chat_mockup';

/** Reveal time of a step kind in a scenario — keeps tests timing-agnostic. */
function stepAt(scenarioIndex: number, kind: string): number {
  const step = SCENARIOS[scenarioIndex].steps.find(s => s.kind === kind);
  if (!step) throw new Error(`unknown step ${kind}`);
  return step.at;
}

/** Advance fake timers to just past the given absolute scenario time. */
function advanceTo(now: { t: number }, target: number): void {
  act(() => vi.advanceTimersByTime(target - now.t));
  now.t = target;
}

function mockReducedMotion(matches: boolean): void {
  Object.defineProperty(window, 'matchMedia', {
    writable: true,
    value: vi.fn().mockImplementation((query: string) => ({
      matches: query === '(prefers-reduced-motion: reduce)' ? matches : false,
      media: query,
      onchange: null,
      addListener: vi.fn(),
      removeListener: vi.fn(),
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
      dispatchEvent: vi.fn(),
    })),
  });
}

describe('ChatMockup (animated)', () => {
  beforeEach(() => {
    mockReducedMotion(false);
    vi.useFakeTimers();
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it('is exposed as a single decorative image', () => {
    render(<ChatMockup />);
    expect(screen.getByRole('img', { name: `${TK}.aria` })).toBeInTheDocument();
  });

  it('types the request into the input before the user bubble lands', () => {
    const { container } = render(<ChatMockup />);
    const now = { t: 0 };
    advanceTo(now, stepAt(0, 'type') + 100);
    // Typing phase: the request text is in the input (split into spans),
    // no user bubble yet, send button still shown.
    expect(container.textContent).toContain(`${TK}.s1_user`);
    expect(container.textContent).toContain(`${TK}.btn_send`);
    expect(screen.queryByText(`${TK}.s1_hitl`)).not.toBeInTheDocument();

    // The user bubble lands and a response starts streaming (Stop button).
    advanceTo(now, stepAt(0, 'user') + 100);
    expect(screen.getByText(`${TK}.s1_user`)).toBeInTheDocument();
    expect(container.textContent).toContain(`${TK}.btn_stop`);
  });

  it('opens the backstage while LIA works, then resolves into the chat', () => {
    const { container } = render(<ChatMockup />);
    const now = { t: 0 };

    // Glass open: backstage label + act-1 figure (gate arrives later).
    advanceTo(now, stepAt(0, 'bs') + 100);
    expect(container.textContent).toContain(`${TK}.backstage_label`);
    expect(container.textContent).toContain(`${TK}.s1_bs_c1`);
    expect(container.textContent).not.toContain(`${TK}.s1_bs_gate`);
    advanceTo(now, stepAt(0, 'bs_gate') + 100);
    expect(container.textContent).toContain(`${TK}.s1_bs_gate`);

    // Glass closed, HITL bubble in the chat, stream window closed (Send back).
    advanceTo(now, stepAt(0, 'hitl') + 100);
    expect(container.textContent).not.toContain(`${TK}.backstage_label`);
    expect(screen.getByText(`${TK}.s1_hitl`)).toBeInTheDocument();
    expect(container.textContent).toContain(`${TK}.btn_send`);

    // Approval and double success; the token bar ticks to the real bill.
    advanceTo(now, stepAt(0, 'done') + 100);
    expect(screen.getByText(`${TK}.s1_approve`)).toBeInTheDocument();
    expect(screen.getByText(`${TK}.s1_done`)).toBeInTheDocument();
    expect(container.textContent).toContain('1 450'); // fr-formatted total tokens
  });

  it('cycles to act 2 after the hold and fade', () => {
    const { container } = render(<ChatMockup />);
    const now = { t: 0 };
    advanceTo(now, SCENARIOS[0].holdMs + 600 + stepAt(1, 'user') + 100);
    expect(container.textContent).toContain(`${TK}.s2_user`);
    expect(container.textContent).not.toContain(`${TK}.s1_user`);
  });

  it('cleans up its timers on unmount', () => {
    const { unmount } = render(<ChatMockup />);
    act(() => vi.advanceTimersByTime(2000));
    unmount();
    expect(vi.getTimerCount()).toBe(0);
  });
});

describe('ChatMockup (reduced motion)', () => {
  it('renders act 1 statically at its resolution moment, without glass', () => {
    mockReducedMotion(true);
    const { container } = render(<ChatMockup />);

    // Full resolution visible at once…
    expect(screen.getByText(`${TK}.s1_user`)).toBeInTheDocument();
    expect(screen.getByText(`${TK}.s1_hitl`)).toBeInTheDocument();
    expect(screen.getByText(`${TK}.s1_approve`)).toBeInTheDocument();
    expect(screen.getByText(`${TK}.s1_done`)).toBeInTheDocument();

    // …no backstage, no typing caret, no stop button, no pending timers.
    expect(container.textContent).not.toContain(`${TK}.backstage_label`);
    expect(container.querySelector('.mockup-caret')).toBeNull();
    expect(container.textContent).toContain(`${TK}.btn_send`);
  });
});
