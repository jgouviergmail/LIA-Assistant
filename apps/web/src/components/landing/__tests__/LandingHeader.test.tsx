/**
 * The landing header's navigation — the row a visitor reads first.
 *
 * Two things about it were decided on measurements rather than taste, and
 * neither is visible in the JSX at a glance:
 *
 *  - the ORDER of the entries is an owner arbitration, and it changed: the
 *    release band used to close the row ("read the product first, its news
 *    last"); it now sits immediately after "Présentation", so the news is the
 *    second thing offered;
 *  - the release entry is EXCLUDED from the row below `lg`. The row appears at
 *    880px and is saturated there: a seventh entry ran the French row 96px past
 *    the viewport (measured). The width itself is guarded in a real browser by
 *    `e2e/smoke/landing-nav-row.spec.ts`; what is guarded HERE is that the
 *    mechanism keeping it out — the responsive class — still exists, since
 *    dropping it is a one-word edit no other unit assertion would notice.
 *
 * The mobile menu carries every entry at every size: it is the row's escape
 * hatch, so the exclusion above must never reach it.
 */

import { act, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

/**
 * Callbacks handed to `IntersectionObserver`. The global stub records nothing,
 * and the scroll spy is only observable by driving them.
 */
const observedCallbacks: IntersectionObserverCallback[] = [];

vi.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (key: string) => key,
    i18n: { language: 'fr', changeLanguage: vi.fn() },
  }),
}));
vi.mock('@/components/LanguageSelector', () => ({
  LanguageSelector: () => <div data-testid="language-selector" />,
}));
vi.mock('@/components/theme-toggle', () => ({
  ThemeToggle: () => <div data-testid="theme-toggle" />,
}));

import { LandingHeader } from '../LandingHeader';

beforeEach(() => {
  observedCallbacks.length = 0;
  vi.stubGlobal(
    'IntersectionObserver',
    class {
      constructor(callback: IntersectionObserverCallback) {
        observedCallbacks.push(callback);
      }
      observe() {}
      unobserve() {}
      disconnect() {}
      takeRecords() {
        return [];
      }
    }
  );
});

afterEach(() => {
  vi.unstubAllGlobals();
});

/**
 * Navigation labels in DOM order. Scoped to the `landing.nav.*` namespace and
 * stripped of the right-hand account actions (which share that namespace) so
 * the logo, the login link and the CTA never shift the assertions.
 */
const ACCOUNT_ACTIONS = ['landing.nav.login', 'landing.nav.get_started'];

function navLabels(): string[] {
  return screen
    .getAllByRole('link')
    .map(link => link.textContent ?? '')
    .filter(label => label.startsWith('landing.nav.') && !ACCOUNT_ACTIONS.includes(label));
}

const PAGE_LINKS_IN_ORDER = [
  'landing.nav.story',
  'landing.nav.philosophy',
  'landing.nav.technical',
  'landing.nav.blog',
  'landing.nav.faq',
  'landing.nav.more',
];

describe('LandingHeader navigation', () => {
  it('lists the release entry immediately after the presentation anchor', () => {
    render(<LandingHeader lng="fr" />);

    const labels = navLabels();
    expect(labels[0]).toBe('landing.nav.features');
    expect(labels[1]).toBe('landing.nav.changelog');
  });

  it('keeps the page links in their arbitrated order, after the anchors', () => {
    render(<LandingHeader lng="fr" />);

    expect(navLabels().slice(2)).toEqual(PAGE_LINKS_IN_ORDER);
  });

  it('keeps the release entry out of the row below lg', () => {
    render(<LandingHeader lng="fr" />);

    const entry = screen.getByRole('link', { name: 'landing.nav.changelog' });
    expect(entry.className).toContain('hidden');
    expect(entry.className).toContain('lg:block');
  });

  it('points every anchor at the home document, so it works from a secondary page', () => {
    // fr is the default locale: `buildLocalizedPath` emits no prefix.
    render(<LandingHeader lng="fr" />);

    expect(screen.getByRole('link', { name: 'landing.nav.features' })).toHaveAttribute(
      'href',
      '/#features'
    );
    expect(screen.getByRole('link', { name: 'landing.nav.changelog' })).toHaveAttribute(
      'href',
      '/#changelog'
    );
  });

  it('prefixes the anchors for a non-default locale', () => {
    render(<LandingHeader lng="en" />);

    expect(screen.getByRole('link', { name: 'landing.nav.changelog' })).toHaveAttribute(
      'href',
      // `buildLocalizedPath('/', 'en')` keeps the home's trailing slash.
      '/en/#changelog'
    );
  });

  it('marks the active section when the observer reports it in view', () => {
    // The scroll spy is what tells a reader where they are in a long page; a
    // silent observer leaves every entry looking equally inactive.
    render(<LandingHeader lng="fr" />);
    const band = document.createElement('section');
    band.id = 'changelog';
    document.body.appendChild(band);

    act(() => {
      observedCallbacks.forEach(callback =>
        // The observer argument is part of the callback contract even though
        // the scroll spy ignores it; omitting it makes the file fail `tsc`.
        callback(
          [{ isIntersecting: true, target: band } as unknown as IntersectionObserverEntry],
          {} as IntersectionObserver
        )
      );
    });

    expect(screen.getByRole('link', { name: 'landing.nav.changelog' }).className).toContain(
      'text-primary'
    );
    band.remove();
  });

  it('turns opaque once the page has scrolled past the transparent band', () => {
    render(<LandingHeader lng="fr" />);
    const banner = screen.getByRole('banner');
    expect(banner.className).toContain('bg-transparent');

    act(() => {
      Object.defineProperty(window, 'scrollY', { value: 200, configurable: true });
      window.dispatchEvent(new Event('scroll'));
    });

    // Transparent over the hero, solid over content — otherwise the links sit
    // on whatever the page happens to be showing behind them.
    expect(banner.className).not.toContain('bg-transparent');
    expect(banner.className).toContain('backdrop-blur-xl');
    Object.defineProperty(window, 'scrollY', { value: 0, configurable: true });
  });

  it('closes the mobile menu on Escape', () => {
    // A menu that only closes by pointer traps a keyboard user behind it.
    render(<LandingHeader lng="fr" />);
    const toggle = screen.getByRole('button', { name: 'common.menu' });
    fireEvent.click(toggle);
    expect(toggle).toHaveAttribute('aria-expanded', 'true');

    fireEvent.keyDown(document, { key: 'Escape' });

    expect(screen.getByRole('button', { name: 'common.menu' })).toHaveAttribute(
      'aria-expanded',
      'false'
    );
  });

  it('offers every entry in the mobile menu, in the same order', () => {
    render(<LandingHeader lng="fr" />);
    fireEvent.click(screen.getByRole('button', { name: 'common.menu' }));

    const labels = navLabels();
    // Both blocks are in the DOM at once (the row is hidden by CSS, not by
    // React), so each entry appears twice — and both must read the same way.
    const anchors = labels.reduce<number[]>(
      (found, label, index) => (label === 'landing.nav.features' ? [...found, index] : found),
      []
    );
    expect(anchors).toHaveLength(2);
    anchors.forEach(index => expect(labels[index + 1]).toBe('landing.nav.changelog'));
    expect(labels.slice(anchors[1] + 2)).toEqual(PAGE_LINKS_IN_ORDER);
  });
});
