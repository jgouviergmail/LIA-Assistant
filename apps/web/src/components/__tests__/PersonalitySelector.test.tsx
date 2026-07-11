/**
 * PersonalitySelector — animated emoji wiring on the header trigger.
 *
 * The dropdown content (hover-to-animate items) is exercised in runtime UAT:
 * Radix menus need real pointer events that jsdom does not deliver reliably.
 */

import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render } from '@testing-library/react';

import { PersonalitySelector } from '../PersonalitySelector';

const PERSONALITY = {
  id: 'p1',
  code: 'cynic',
  emoji: '😏',
  is_default: true,
  title: 'Cynique',
  description: 'Esprit sarcastique',
};

const mockReturn = {
  personalities: [PERSONALITY],
  currentPersonality: PERSONALITY as typeof PERSONALITY | null,
  currentPersonalityId: 'p1' as string | null,
  loading: false,
  updating: false,
  error: null,
  updatePersonality: vi.fn(),
  refetch: vi.fn(),
};

vi.mock('@/hooks/usePersonality', () => ({
  usePersonality: () => mockReturn,
}));

describe('PersonalitySelector', () => {
  beforeEach(() => {
    mockReturn.loading = false;
    mockReturn.currentPersonality = PERSONALITY;
  });

  it('always animates the current personality emoji in the header trigger', () => {
    const { container } = render(<PersonalitySelector />);
    const img = container.querySelector('img');
    expect(img).not.toBeNull();
    expect(img?.getAttribute('src')).toBe('/animated-emoji/1f60f.webp');
  });

  it('falls back to the default static glyph when no personality is selected', () => {
    mockReturn.currentPersonality = null;
    const { container } = render(<PersonalitySelector />);
    // Default emoji ⚖️ still goes through AnimatedEmoji (derived codepoint).
    expect(container.querySelector('img')?.getAttribute('src')).toBe(
      '/animated-emoji/2696-fe0f.webp'
    );
  });

  it('renders the loading state without any emoji', () => {
    mockReturn.loading = true;
    const { container } = render(<PersonalitySelector />);
    expect(container.querySelector('img')).toBeNull();
  });
});
