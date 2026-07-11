/**
 * AnimatedEmoji — codepoint derivation, animation gating, error and
 * reduced-motion fallbacks.
 */

import { describe, it, expect, vi, afterEach } from 'vitest';
import { render, fireEvent, screen } from '@testing-library/react';

import { AnimatedEmoji, emojiToCodepoint } from '../animated-emoji';

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

describe('emojiToCodepoint', () => {
  it('derives single and multi-codepoint sequences (variation selector included)', () => {
    expect(emojiToCodepoint('😏')).toBe('1f60f');
    expect(emojiToCodepoint('⚖️')).toBe('2696-fe0f');
    expect(emojiToCodepoint('✨')).toBe('2728');
  });
});

describe('AnimatedEmoji', () => {
  it('renders the animated WebP derived from the glyph when animate is set', () => {
    const { container } = render(<AnimatedEmoji glyph="⚖️" animate />);
    const img = container.querySelector('img');
    expect(img?.getAttribute('src')).toBe('/animated-emoji/2696-fe0f.webp');
    expect(img?.getAttribute('alt')).toBe('');
  });

  it('prefers an explicit codepoint override over derivation', () => {
    const { container } = render(<AnimatedEmoji glyph="😊" codepoint="1f60a" animate />);
    expect(container.querySelector('img')?.getAttribute('src')).toBe('/animated-emoji/1f60a.webp');
  });

  it('renders the static glyph when animate is false', () => {
    const { container } = render(<AnimatedEmoji glyph="😏" />);
    expect(container.querySelector('img')).toBeNull();
    expect(screen.getByText('😏')).toBeInTheDocument();
  });

  it('falls back to the static glyph when the asset fails to load', () => {
    const { container } = render(<AnimatedEmoji glyph="🥟" animate />);
    fireEvent.error(container.querySelector('img') as HTMLImageElement);
    expect(container.querySelector('img')).toBeNull();
    expect(screen.getByText('🥟')).toBeInTheDocument();
  });

  it('does not render (nor fetch) the WebP under prefers-reduced-motion', () => {
    mockReducedMotion(true);
    const { container } = render(<AnimatedEmoji glyph="😏" animate />);
    expect(container.querySelector('img')).toBeNull();
    expect(screen.getByText('😏')).toBeInTheDocument();
  });
});
