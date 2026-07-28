/**
 * InteractiveChatMockup — the /demo upgrade (UX P12): the same four-act
 * mockup as the landing hero, wrapped with REAL controls. Scene pastilles
 * select an act, pause/replay drive the schedule, the auto loop survives
 * untouched until the first interaction, and reduced motion swaps static
 * resolution frames without ever scheduling a timer.
 *
 * The controls live OUTSIDE the `role="img"` element (a decorative image
 * cannot contain interactive content); the i18n mock echoes keys.
 */

import { act, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { buildLocalizedPath } from '@/utils/i18n-path-utils';
import type { Language } from '@/i18n/settings';

vi.mock('next/link', () => ({
  default: ({ children, href, ...props }: React.ComponentProps<'a'> & { href: string }) => (
    <a href={href} {...props}>
      {children}
    </a>
  ),
}));

import { InteractiveChatMockup } from '../InteractiveChatMockup';
import { SCENARIOS } from '../mockup/scenarios';
import { CYCLE_FADE_MS } from '../mockup/useMockupTimeline';

const TK = 'landing.chat_mockup';

/** Reveal time of a step kind in a scenario — keeps tests timing-agnostic. */
function stepAt(scenarioIndex: number, kind: string): number {
  const step = SCENARIOS[scenarioIndex].steps.find(s => s.kind === kind);
  if (!step) throw new Error(`unknown step ${kind}`);
  return step.at;
}

function advance(ms: number): void {
  act(() => vi.advanceTimersByTime(ms));
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

function sceneButton(chipKey: string): HTMLElement {
  return screen.getByRole('button', { name: `${TK}.${chipKey}` });
}

describe('InteractiveChatMockup (animated)', () => {
  beforeEach(() => {
    mockReducedMotion(false);
    vi.useFakeTimers();
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it('keeps the decorative image and the auto loop until someone interacts', () => {
    const { container } = render(<InteractiveChatMockup lng="fr" />);
    expect(screen.getByRole('img', { name: `${TK}.aria` })).toBeInTheDocument();

    advance(SCENARIOS[0].holdMs + CYCLE_FADE_MS + stepAt(1, 'user') + 100);
    expect(container.textContent).toContain(`${TK}.s2_user`);
  });

  it('offers one labelled scene button per act, the active one pressed', () => {
    render(<InteractiveChatMockup lng="fr" />);
    for (const scenario of SCENARIOS) {
      expect(sceneButton(scenario.chipKey)).toBeInTheDocument();
    }
    expect(sceneButton('s1_chip')).toHaveAttribute('aria-pressed', 'true');
    expect(sceneButton('s3_chip')).toHaveAttribute('aria-pressed', 'false');
  });

  it('plays a selected scene once and freezes on its resolution frame', () => {
    const { container } = render(<InteractiveChatMockup lng="fr" />);
    fireEvent.click(sceneButton('s3_chip'));

    advance(stepAt(2, 'user') + 100);
    expect(container.textContent).toContain(`${TK}.s3_user`);

    // Far past the act's hold: no cross-fade to act 4, the scene is frozen.
    advance(SCENARIOS[2].holdMs + CYCLE_FADE_MS + 5_000);
    expect(container.textContent).toContain(`${TK}.s3_done`);
    expect(container.textContent).not.toContain(`${TK}.s4_user`);
    // The frozen scene reads as paused — the control now offers to replay.
    expect(screen.getByRole('button', { name: `${TK}.demo_play` })).toBeInTheDocument();
  });

  it('pause freezes the schedule where it is, play resumes it', () => {
    const { container } = render(<InteractiveChatMockup lng="fr" />);
    advance(stepAt(0, 'user') - 200);
    fireEvent.click(screen.getByRole('button', { name: `${TK}.demo_pause` }));

    advance(10_000);
    expect(screen.queryByText(`${TK}.s1_user`)).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: `${TK}.demo_play` }));
    advance(300);
    expect(container.textContent).toContain(`${TK}.s1_user`);
  });

  it('replays the current scene from its first beat', () => {
    const { container } = render(<InteractiveChatMockup lng="fr" />);
    fireEvent.click(sceneButton('s2_chip'));
    advance(stepAt(1, 'user') + 100);
    expect(screen.getByText(`${TK}.s2_user`)).toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: `${TK}.demo_replay` }));
    expect(screen.queryByText(`${TK}.s2_user`)).not.toBeInTheDocument();

    advance(stepAt(1, 'user') + 100);
    expect(container.textContent).toContain(`${TK}.s2_user`);
  });

  it('links the final CTA to the register journey', () => {
    render(<InteractiveChatMockup lng="fr" />);
    expect(screen.getByRole('link', { name: 'landing.hero.cta_primary' })).toHaveAttribute(
      'href',
      buildLocalizedPath('/register', 'fr' as Language)
    );
  });

  it('hides the CTA in hero context (withCta false) — the hero owns its own', () => {
    render(<InteractiveChatMockup lng="fr" withCta={false} />);
    expect(screen.queryByRole('link', { name: 'landing.hero.cta_primary' })).toBeNull();
    // The controls stay — only the duplicate CTA goes away.
    expect(sceneButton('s1_chip')).toBeInTheDocument();
  });

  /**
   * Stage behaviors migrated from ChatMockup.test on the hero transplant
   * (ChatMockup was deleted once the hero adopted this component): typing
   * phase, backstage window, stream chrome and the token-bar tick are ENGINE
   * + STAGE contracts, and this is now their only consumer-level harness.
   */
  it('types the request into the input before the user bubble lands', () => {
    const { container } = render(<InteractiveChatMockup lng="fr" />);
    advance(stepAt(0, 'type') + 100);
    expect(container.textContent).toContain(`${TK}.s1_user`);
    expect(container.textContent).toContain(`${TK}.btn_send`);
    expect(screen.queryByText(`${TK}.s1_hitl`)).not.toBeInTheDocument();

    advance(stepAt(0, 'user') - stepAt(0, 'type'));
    expect(screen.getByText(`${TK}.s1_user`)).toBeInTheDocument();
    expect(container.textContent).toContain(`${TK}.btn_stop`);
  });

  it('opens the backstage while LIA works, then resolves into the chat', () => {
    const { container } = render(<InteractiveChatMockup lng="fr" />);

    advance(stepAt(0, 'bs') + 100);
    expect(container.textContent).toContain(`${TK}.backstage_label`);
    expect(container.textContent).toContain(`${TK}.s1_bs_c1`);
    expect(container.textContent).not.toContain(`${TK}.s1_bs_gate`);
    advance(stepAt(0, 'bs_gate') - stepAt(0, 'bs'));
    expect(container.textContent).toContain(`${TK}.s1_bs_gate`);

    advance(stepAt(0, 'hitl') - stepAt(0, 'bs_gate'));
    expect(container.textContent).not.toContain(`${TK}.backstage_label`);
    expect(screen.getByText(`${TK}.s1_hitl`)).toBeInTheDocument();
    expect(container.textContent).toContain(`${TK}.btn_send`);

    advance(stepAt(0, 'done') - stepAt(0, 'hitl'));
    expect(screen.getByText(`${TK}.s1_approve`)).toBeInTheDocument();
    expect(screen.getByText(`${TK}.s1_done`)).toBeInTheDocument();
    expect(container.textContent).toContain('1 450'); // fr-formatted total tokens
  });

  it('cleans up its timers on unmount', () => {
    const { unmount } = render(<InteractiveChatMockup lng="fr" />);
    advance(2_000);
    unmount();
    expect(vi.getTimerCount()).toBe(0);
  });
});

describe('InteractiveChatMockup (reduced motion)', () => {
  beforeEach(() => {
    mockReducedMotion(true);
    vi.useFakeTimers();
  });

  afterEach(() => {
    mockReducedMotion(false);
    vi.useRealTimers();
  });

  it('swaps static resolution frames on selection, without any timers', () => {
    const { container } = render(<InteractiveChatMockup lng="fr" />);
    // Act 1 fully resolved at once, no glass, no typing caret, no stop chrome
    // (assertions migrated from ChatMockup.test on the hero transplant).
    expect(screen.getByText(`${TK}.s1_user`)).toBeInTheDocument();
    expect(screen.getByText(`${TK}.s1_hitl`)).toBeInTheDocument();
    expect(screen.getByText(`${TK}.s1_approve`)).toBeInTheDocument();
    expect(screen.getByText(`${TK}.s1_done`)).toBeInTheDocument();
    expect(container.textContent).not.toContain(`${TK}.backstage_label`);
    expect(container.querySelector('.mockup-caret')).toBeNull();
    expect(container.textContent).toContain(`${TK}.btn_send`);

    fireEvent.click(sceneButton('s4_chip'));
    expect(container.textContent).toContain(`${TK}.s4_user`);
    expect(vi.getTimerCount()).toBe(0);
  });

  it('hides pause and replay when nothing animates', () => {
    render(<InteractiveChatMockup lng="fr" />);
    expect(screen.queryByRole('button', { name: `${TK}.demo_pause` })).toBeNull();
    expect(screen.queryByRole('button', { name: `${TK}.demo_replay` })).toBeNull();
  });
});
