/**
 * Active RAG spaces indicator — its accessible name (S5b, revised).
 *
 * The plan said "hide it on mobile to reclaim room". Measurement said
 * otherwise: the chat header reachability suite passes at every width, so the
 * row is not saturated and removing the badge would cost information — which
 * spaces are feeding LIA's answers — for no gain.
 *
 * What the measurement DID reveal is a real defect next door: below `sm` the
 * badge renders a bare count beside an icon, so the link's accessible name was
 * the string "2". The `title` that would have explained it is a hover
 * affordance, and touch has no hover. The name now lives on the link and is
 * identical at every width.
 */

import { describe, it, expect, vi } from 'vitest';

import { renderWithProviders, screen } from '@/__tests__/test-utils';

const { useActiveSpaces } = vi.hoisted(() => ({ useActiveSpaces: vi.fn() }));

vi.mock('@/hooks/useSpaces', async importOriginal => {
  const actual = await importOriginal<typeof import('@/hooks/useSpaces')>();
  return { ...actual, useActiveSpaces };
});
vi.mock('next/navigation', () => ({ usePathname: () => '/fr/dashboard/chat' }));

import { ActiveSpacesIndicator } from '../ActiveSpacesIndicator';

describe('ActiveSpacesIndicator', () => {
  it('says nothing while loading', () => {
    useActiveSpaces.mockReturnValue({ activeCount: 3, loading: true });
    const { container } = renderWithProviders(<ActiveSpacesIndicator />);
    expect(container).toBeEmptyDOMElement();
  });

  it('says nothing when no space is active', () => {
    useActiveSpaces.mockReturnValue({ activeCount: 0, loading: false });
    const { container } = renderWithProviders(<ActiveSpacesIndicator />);
    expect(container).toBeEmptyDOMElement();
  });

  it('names the link explicitly rather than by its bare count', () => {
    // The whole point: below `sm` the visible text is just "2".
    useActiveSpaces.mockReturnValue({ activeCount: 2, loading: false });
    renderWithProviders(<ActiveSpacesIndicator />);

    const link = screen.getByRole('link');
    const name = link.getAttribute('aria-label') ?? '';
    expect(name).toBe('spaces.indicator_tooltip');
    expect(name).not.toBe('2');
  });

  it('leads to the spaces page in the current locale', () => {
    useActiveSpaces.mockReturnValue({ activeCount: 1, loading: false });
    renderWithProviders(<ActiveSpacesIndicator />);
    // The locale prefix is the app's business (`buildLocalizedPath` may omit
    // the default one); what this pins is the destination.
    expect(screen.getByRole('link').getAttribute('href')).toContain('/dashboard/spaces');
  });

  it('keeps the decorative icon out of the accessible name', () => {
    useActiveSpaces.mockReturnValue({ activeCount: 1, loading: false });
    const { container } = renderWithProviders(<ActiveSpacesIndicator />);
    const icon = container.querySelector('svg');
    expect(icon).toHaveAttribute('aria-hidden', 'true');
  });

  it('still shows the count visually', () => {
    // The information itself is preserved — this lot renames, it does not hide.
    useActiveSpaces.mockReturnValue({ activeCount: 4, loading: false });
    renderWithProviders(<ActiveSpacesIndicator />);
    expect(screen.getByText('4')).toBeInTheDocument();
  });
});
