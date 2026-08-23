/**
 * The 404 page.
 *
 * Before it existed, a missing page fell through to Next's built-in default:
 * untranslated, unstyled, and with no way back into the app.
 */

import { describe, it, expect, vi } from 'vitest';

import { renderWithProviders, screen } from '@/__tests__/test-utils';

const { pathname } = vi.hoisted(() => ({ pathname: { value: '/fr/nowhere' } }));
vi.mock('next/navigation', () => ({ usePathname: () => pathname.value }));

import NotFound from '../not-found';

describe('NotFound', () => {
  it('announces itself with a single h1', () => {
    renderWithProviders(<NotFound />);
    const headings = screen.getAllByRole('heading', { level: 1 });
    expect(headings).toHaveLength(1);
    expect(headings[0]).toHaveTextContent('errors.not_found');
  });

  it('explains what happened rather than only naming the code', () => {
    renderWithProviders(<NotFound />);
    expect(screen.getByText('errors.not_found_description')).toBeInTheDocument();
  });

  it('offers a way back home', () => {
    renderWithProviders(<NotFound />);
    expect(screen.getByRole('link', { name: 'errors.go_home' })).toBeInTheDocument();
  });

  it.each([
    // The default locale carries NO prefix — the middleware runs with
    // `prefixDefault: false`, so `/fr` would only bounce through a redirect.
    ['/anything', '/'],
    ['/fr/anything', '/'],
    // next/link normalises the trailing slash away, hence '/es' not '/es/'.
    ['/es/anything', '/es'],
    ['/de/deep/path', '/de'],
  ])('sends a visitor on %s back to their own home', (from, expected) => {
    // Hardcoding "/" would drop a Spanish visitor onto the default locale —
    // a second wrong page in answer to the first.
    pathname.value = from;
    renderWithProviders(<NotFound />);
    expect(screen.getByRole('link', { name: 'errors.go_home' })).toHaveAttribute('href', expected);
  });

  it('renders a landmark so the page is navigable', () => {
    pathname.value = '/fr/nowhere';
    renderWithProviders(<NotFound />);
    expect(screen.getByRole('main')).toBeInTheDocument();
  });
});
