/**
 * AssistantAvatar — animated emoji gating: latest-message prop, reduced motion,
 * onError fallback (spec D-5/D-6).
 */

import { describe, it, expect, vi, afterEach } from 'vitest';
import { render, fireEvent, screen } from '@testing-library/react';

import { AssistantAvatar } from '../AssistantAvatar';
import type { PsycheStateSummary } from '@/types/psyche';

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

/** Reinstall the setup.ts matchMedia mock with a chosen reduced-motion answer. */
function mockReducedMotion(matches: boolean): void {
  window.matchMedia = vi.fn().mockImplementation((query: string) => ({
    matches: query.includes('prefers-reduced-motion') ? matches : false,
    media: query,
    onchange: null,
    addListener: vi.fn(),
    removeListener: vi.fn(),
    addEventListener: vi.fn(),
    removeEventListener: vi.fn(),
    dispatchEvent: vi.fn(),
  }));
}

afterEach(() => mockReducedMotion(false));

describe('AssistantAvatar animated emoji', () => {
  it('renders the animated WebP for the latest assistant message', () => {
    const { container } = render(<AssistantAvatar psycheState={PSYCHE} animateEmoji />);
    const img = container.querySelector('img');
    expect(img).not.toBeNull();
    expect(img?.getAttribute('src')).toBe('/animated-emoji/1f61c.webp');
    expect(img?.getAttribute('alt')).toBe('');
  });

  it('renders the static glyph when animateEmoji is false (history rows)', () => {
    const { container } = render(<AssistantAvatar psycheState={PSYCHE} />);
    expect(container.querySelector('img')).toBeNull();
    expect(screen.getByText('😜')).toBeInTheDocument();
  });

  it('falls back to the static glyph when the asset fails to load', () => {
    const { container } = render(<AssistantAvatar psycheState={PSYCHE} animateEmoji />);
    fireEvent.error(container.querySelector('img') as HTMLImageElement);
    expect(container.querySelector('img')).toBeNull();
    expect(screen.getByText('😜')).toBeInTheDocument();
  });

  it('does not render (nor fetch) the WebP under prefers-reduced-motion', () => {
    mockReducedMotion(true);
    const { container } = render(<AssistantAvatar psycheState={PSYCHE} animateEmoji />);
    expect(container.querySelector('img')).toBeNull();
    expect(screen.getByText('😜')).toBeInTheDocument();
  });

  it('keeps the classic LIA fallback when psyche is disabled', () => {
    const { container } = render(<AssistantAvatar psycheState={null} animateEmoji />);
    expect(container.querySelector('img')).toBeNull();
    expect(screen.getByText('LIA')).toBeInTheDocument();
  });

  it('wakes a history snapshot while hovered, sleeps on leave (I1)', () => {
    const { container } = render(<AssistantAvatar psycheState={PSYCHE} />);
    const wrapper = container.firstChild as HTMLElement;
    expect(container.querySelector('img')).toBeNull();

    fireEvent.mouseEnter(wrapper);
    expect(container.querySelector('img')?.getAttribute('src')).toBe('/animated-emoji/1f61c.webp');

    fireEvent.mouseLeave(wrapper);
    expect(container.querySelector('img')).toBeNull();
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
