/**
 * AssistantAvatar — portrait playback: latest-message prop, reduced motion,
 * viewport suspension and frozen historical mood.
 */

import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { act, cleanup, render, fireEvent, screen } from '@testing-library/react';

import { AssistantAvatar } from '../AssistantAvatar';
import type { PsycheStateSummary } from '@/types/psyche';
import {
  installSpiritBrowser,
  SpiritIntersectionObserver,
} from '@/components/spirit/__tests__/browser';
import { activeFrameSubscribers } from '@/components/eyes/rig/scheduler';

const PSYCHE: PsycheStateSummary = {
  mood_label: 'playful',
  mood_color: '#f472b6',
  mood_pleasure: 0.5,
  mood_arousal: 0.4,
  mood_dominance: 0.1,
  active_emotion: 'amusement',
  emotion_intensity: 0.7,
  relationship_stage: 'ORIENTATION',
};

let browser: ReturnType<typeof installSpiritBrowser>;
beforeEach(() => {
  browser = installSpiritBrowser();
});
function mockReducedMotion(matches: boolean): void {
  act(() => browser.setMotion(matches));
}
afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
});

function showPortrait(container: HTMLElement, visible = true) {
  const target = container.querySelector('[data-companion-portrait]');
  if (!target) throw new Error('Selected portrait missing');
  const observer = SpiritIntersectionObserver.instances.find(instance =>
    instance.targets.has(target)
  );
  if (!observer) throw new Error('Portrait visibility observer missing');
  observer.notify(target, visible);
}

function expectStillPortrait(container: HTMLElement, expression = 'joy') {
  expect(container.querySelector('.lia-eyes')).toHaveAttribute('data-expression', expression);
  expect(container.querySelector('.lia-eyes')).toHaveAttribute('data-motion', 'off');
  expect(container.querySelector('.lia-eyes')).toHaveAttribute('data-life', 'off');
  expect(container.querySelectorAll('canvas, img')).toHaveLength(0);
  expect(activeFrameSubscribers()).toBe(0);
}

describe('AssistantAvatar emotional portrait', () => {
  it('renders the current native face and wakes only a visible latest message', () => {
    const { container } = render(<AssistantAvatar psycheState={PSYCHE} animateEmoji />);
    expectStillPortrait(container);
    expect(container.querySelector('[data-character="spirit"]')).toHaveStyle({
      '--spirit-body-url': "url('/avatars/spirit/v2/female/body.webp')",
    });
    expect(container.querySelector('[data-rig-mouth]')?.getAttribute('d')).toBeTruthy();
    act(() => showPortrait(container));
    expect(container.querySelector('.lia-eyes')).not.toHaveAttribute('data-motion', 'off');
    expect(activeFrameSubscribers()).toBe(1);
  });

  it('renders the frozen portrait when animateEmoji is false (history rows)', () => {
    const { container } = render(<AssistantAvatar psycheState={PSYCHE} />);
    act(() => showPortrait(container));
    expectStillPortrait(container);
  });

  it('suspends the current portrait when it leaves the viewport', () => {
    const { container } = render(<AssistantAvatar psycheState={PSYCHE} animateEmoji />);
    act(() => showPortrait(container));
    expect(activeFrameSubscribers()).toBe(1);
    act(() => showPortrait(container, false));
    expectStillPortrait(container);
  });

  it('keeps the native face static under prefers-reduced-motion', () => {
    mockReducedMotion(true);
    const { container } = render(<AssistantAvatar psycheState={PSYCHE} animateEmoji />);
    act(() => showPortrait(container));
    expectStillPortrait(container);
  });

  it('keeps the selected neutral portrait when psyche is disabled', () => {
    const { container } = render(<AssistantAvatar psycheState={null} animateEmoji />);
    expectStillPortrait(container, 'neutral');
    expect(screen.queryByText('LIA')).not.toBeInTheDocument();
  });

  it('wakes a history snapshot while hovered, sleeps on leave (I1)', () => {
    const { container } = render(<AssistantAvatar psycheState={PSYCHE} />);
    const wrapper = container.firstChild as HTMLElement;
    act(() => showPortrait(container));
    expectStillPortrait(container);

    fireEvent.mouseEnter(wrapper);
    expect(container.querySelector('.lia-eyes')).not.toHaveAttribute('data-motion', 'off');
    expect(activeFrameSubscribers()).toBe(1);

    fireEvent.mouseLeave(wrapper);
    expectStillPortrait(container);
  });

  it('uses the selected masculine identity without changing the saved mood', () => {
    const { container } = render(<AssistantAvatar psycheState={PSYCHE} variant="male" />);
    expectStillPortrait(container);
    expect(container.querySelector('[data-character="spirit"]')).toHaveAttribute(
      'data-spirit-companion',
      'male'
    );
    expect(container.querySelector('[data-character="spirit"]')).toHaveStyle({
      '--spirit-body-url': "url('/avatars/spirit/v2/male/body.webp')",
    });
    expect(container.querySelector('[data-companion-portrait]')).toHaveClass(
      'lia-message-portrait'
    );
  });

  it('keeps the portrait fixed until the identity preference has hydrated', () => {
    const { container } = render(
      <AssistantAvatar psycheState={PSYCHE} animateEmoji animationReady={false} />
    );
    act(() => showPortrait(container));
    fireEvent.mouseEnter(container.firstChild as HTMLElement);
    expectStillPortrait(container);
  });
});

describe('AssistantAvatar emotion particles (W3)', () => {
  const strong = (emotion: string, intensity = 0.9) => ({
    ...PSYCHE,
    active_emotion: emotion,
    emotion_intensity: intensity,
  });

  it('bursts 3 particles when a whitelisted strong emotion arrives', () => {
    const { container, rerender } = render(<AssistantAvatar psycheState={PSYCHE} animateEmoji />);
    rerender(<AssistantAvatar psycheState={strong('tenderness')} animateEmoji />);
    const particles = container.querySelectorAll('.animate-particle-up');
    expect(particles).toHaveLength(3);
    expect(particles[0].textContent).toBe('❤️');
  });

  it('never bursts on initial mount, even with a strong emotion', () => {
    const { container } = render(
      <AssistantAvatar psycheState={strong('tenderness')} animateEmoji />
    );
    expect(container.querySelector('.animate-particle-up')).toBeNull();
  });

  it('stays quiet below the intensity threshold', () => {
    const { container, rerender } = render(<AssistantAvatar psycheState={PSYCHE} animateEmoji />);
    rerender(<AssistantAvatar psycheState={strong('tenderness', 0.5)} animateEmoji />);
    expect(container.querySelector('.animate-particle-up')).toBeNull();
  });

  it('stays quiet for non-whitelisted emotions', () => {
    const { container, rerender } = render(<AssistantAvatar psycheState={PSYCHE} animateEmoji />);
    rerender(<AssistantAvatar psycheState={strong('confusion')} animateEmoji />);
    expect(container.querySelector('.animate-particle-up')).toBeNull();
  });

  it('stays quiet on history rows (animateEmoji false)', () => {
    const { container, rerender } = render(<AssistantAvatar psycheState={PSYCHE} />);
    rerender(<AssistantAvatar psycheState={strong('tenderness')} />);
    expect(container.querySelector('.animate-particle-up')).toBeNull();
  });

  it('stays quiet under prefers-reduced-motion', () => {
    mockReducedMotion(true);
    const { container, rerender } = render(<AssistantAvatar psycheState={PSYCHE} animateEmoji />);
    rerender(<AssistantAvatar psycheState={strong('tenderness')} animateEmoji />);
    expect(container.querySelector('.animate-particle-up')).toBeNull();
  });
});

describe('AssistantAvatar mood-ring ping (I6)', () => {
  it('never pings on initial mount', () => {
    const { container } = render(<AssistantAvatar psycheState={PSYCHE} animateEmoji />);
    expect(container.querySelector('.animate-mood-ping')).toBeNull();
  });

  it('pings the live avatar when the mood changes, not history snapshots', () => {
    const { container, rerender } = render(<AssistantAvatar psycheState={PSYCHE} animateEmoji />);

    rerender(<AssistantAvatar psycheState={{ ...PSYCHE, mood_label: 'serene' }} animateEmoji />);
    expect(container.querySelector('.animate-mood-ping')).not.toBeNull();
  });

  it('does not ping when animateEmoji is false (history rows)', () => {
    const { container, rerender } = render(<AssistantAvatar psycheState={PSYCHE} />);

    rerender(<AssistantAvatar psycheState={{ ...PSYCHE, mood_label: 'serene' }} />);
    expect(container.querySelector('.animate-mood-ping')).toBeNull();
  });
});
