/**
 * Content contract of the two gallery tabs.
 *
 * The carousel's behaviour is covered by LandingCarousel.test.tsx; what is at
 * stake here is what each tab FEEDS it: the full capture inventory, the full
 * deck, distinct names, and the deliberate asymmetry on the full-screen view
 * (captures are dense and light, a deck slide is already served at its
 * readable width and weighs 2 MB).
 *
 * The global i18n stub echoes keys and drops interpolation, which would give
 * the 15 slides one identical name — so this file installs a stub that keeps
 * the variables.
 */

import { render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

vi.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (key: string, vars?: Record<string, string | number>) =>
      vars ? `${key}(${Object.values(vars).join(',')})` : key,
    i18n: { language: 'fr', changeLanguage: vi.fn() },
  }),
}));

import { PresentationSection } from '../PresentationSection';
import { ScreenshotsSection } from '../ScreenshotsSection';

/** Thumbnails are the only per-slide named controls: one per view. */
function thumbnailNames(): string[] {
  return screen
    .getAllByRole('button')
    .map(b => b.getAttribute('aria-label') ?? '')
    .filter(name => !name.startsWith('common.'));
}

describe('ScreenshotsSection', () => {
  it('feeds the carousel the 12 captures, each with its own name', () => {
    render(<ScreenshotsSection />);

    const names = thumbnailNames();
    expect(names).toHaveLength(12);
    expect(new Set(names).size).toBe(12);
    expect(names[0]).toBe('landing.screenshots.items.homepage');
  });

  it('offers the full-screen view (a capture is unreadable at 544 px)', () => {
    render(<ScreenshotsSection />);
    expect(screen.getByRole('button', { name: 'common.expand_image' })).toBeInTheDocument();
  });
});

describe('PresentationSection', () => {
  it('feeds the carousel the 15 slides in order', () => {
    render(<PresentationSection />);

    const names = thumbnailNames();
    expect(names).toHaveLength(15);
    expect(names[0]).toBe('landing.presentation.slide_alt(1)');
    expect(names[14]).toBe('landing.presentation.slide_alt(15)');
  });

  it('captions each slide with its position — the deck has no other title', () => {
    const { container } = render(<PresentationSection />);
    expect(container.querySelector('[aria-live="polite"]')).toHaveTextContent(
      'landing.presentation.slide_counter(1,15)'
    );
  });

  it('does not offer the full-screen view (a slide is a 2 MB asset)', () => {
    render(<PresentationSection />);
    expect(screen.queryByRole('button', { name: 'common.expand_image' })).toBeNull();
  });
});
