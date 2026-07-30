/**
 * Active RAG spaces indicator — quick-toggle menu (R01, extends S5b).
 *
 * History: S5b gave the badge an explicit accessible name (below `sm` the
 * visible text is the bare count, and `title` is hover-only). R01 turns the
 * bare link into a menu of per-space switches so activation is two taps from
 * the chat — and, crucially, renders the trigger whenever the user HAS
 * spaces: the old `activeCount === 0 → null` rule hid the surface exactly
 * when it was needed to activate the first space.
 *
 * What must hold:
 *  - loading or zero EXISTING spaces → nothing;
 *  - spaces exist (even zero active) → a named trigger with the count;
 *  - each space is a menuitemcheckbox reflecting `is_active`, and toggling
 *    calls the API without closing the menu (batch toggling);
 *  - the management page stays one item away (the gesture the link provided).
 */

import { describe, it, expect, vi, beforeEach } from 'vitest';

import { renderWithProviders, screen } from '@/__tests__/test-utils';

const { useSpaces, toggleSpace } = vi.hoisted(() => ({
  useSpaces: vi.fn(),
  toggleSpace: vi.fn(),
}));

vi.mock('@/hooks/useSpaces', async importOriginal => {
  const actual = await importOriginal<typeof import('@/hooks/useSpaces')>();
  return { ...actual, useSpaces };
});
vi.mock('next/navigation', () => ({ usePathname: () => '/fr/dashboard/chat' }));
vi.mock('sonner', () => ({ toast: { error: vi.fn(), success: vi.fn() } }));

import { ActiveSpacesIndicator } from '../ActiveSpacesIndicator';

interface SpaceStub {
  id: string;
  name: string;
  is_active: boolean;
}

function hookValue(spaces: SpaceStub[], overrides: Record<string, unknown> = {}) {
  return {
    spaces,
    activeCount: spaces.filter(s => s.is_active).length,
    loading: false,
    toggleSpace,
    toggling: false,
    ...overrides,
  };
}

const TWO_SPACES: SpaceStub[] = [
  { id: 's1', name: 'Droit', is_active: true },
  { id: 's2', name: 'Cuisine', is_active: false },
];

beforeEach(() => {
  toggleSpace.mockReset();
  toggleSpace.mockResolvedValue({ is_active: true });
});

describe('ActiveSpacesIndicator — visibility', () => {
  it('says nothing while loading', () => {
    useSpaces.mockReturnValue(hookValue(TWO_SPACES, { loading: true }));
    const { container } = renderWithProviders(<ActiveSpacesIndicator />);
    expect(container).toBeEmptyDOMElement();
  });

  it('renders even with no space at all — the only one-click door to the page', () => {
    // Since the nav slot went to Relations (2026-07-30), this pill is how a
    // brand-new user reaches the spaces page to create their first space.
    useSpaces.mockReturnValue(hookValue([]));
    renderWithProviders(<ActiveSpacesIndicator />);
    expect(screen.getByRole('button', { name: 'spaces.indicator_tooltip' })).toBeInTheDocument();
  });

  it('renders when spaces exist even with zero active — the activation entry point', () => {
    useSpaces.mockReturnValue(hookValue(TWO_SPACES.map(s => ({ ...s, is_active: false }))));
    renderWithProviders(<ActiveSpacesIndicator />);
    expect(screen.getByRole('button', { name: 'spaces.indicator_tooltip' })).toBeInTheDocument();
  });
});

describe('ActiveSpacesIndicator — the trigger', () => {
  it('names the trigger explicitly rather than by its bare count (S5b invariant)', () => {
    useSpaces.mockReturnValue(hookValue(TWO_SPACES));
    renderWithProviders(<ActiveSpacesIndicator />);

    const trigger = screen.getByRole('button');
    const name = trigger.getAttribute('aria-label') ?? '';
    expect(name).toBe('spaces.indicator_tooltip');
    expect(name).not.toBe('1');
  });

  it('still shows the active count visually', () => {
    useSpaces.mockReturnValue(hookValue(TWO_SPACES));
    renderWithProviders(<ActiveSpacesIndicator />);
    expect(screen.getByText('1')).toBeInTheDocument();
  });

  it('keeps the decorative icon out of the accessible name', () => {
    useSpaces.mockReturnValue(hookValue(TWO_SPACES));
    const { container } = renderWithProviders(<ActiveSpacesIndicator />);
    expect(container.querySelector('svg')).toHaveAttribute('aria-hidden', 'true');
  });
});

describe('ActiveSpacesIndicator — the menu', () => {
  it('lists every space as a checkbox reflecting its activation state', async () => {
    useSpaces.mockReturnValue(hookValue(TWO_SPACES));
    const { user } = renderWithProviders(<ActiveSpacesIndicator />);
    await user.click(screen.getByRole('button'));

    const active = await screen.findByRole('menuitemcheckbox', { name: 'Droit' });
    const inactive = await screen.findByRole('menuitemcheckbox', { name: 'Cuisine' });
    expect(active).toHaveAttribute('aria-checked', 'true');
    expect(inactive).toHaveAttribute('aria-checked', 'false');
  });

  it('toggles a space through the API without closing the menu', async () => {
    useSpaces.mockReturnValue(hookValue(TWO_SPACES));
    const { user } = renderWithProviders(<ActiveSpacesIndicator />);
    await user.click(screen.getByRole('button'));

    await user.click(await screen.findByRole('menuitemcheckbox', { name: 'Cuisine' }));

    expect(toggleSpace).toHaveBeenCalledWith('s2');
    // Batch toggling: the other switch must still be reachable.
    expect(screen.getByRole('menuitemcheckbox', { name: 'Droit' })).toBeInTheDocument();
  });

  it('says a failed toggle out loud instead of rejecting unhandled', async () => {
    // The reverted switch may be OFF-SCREEN (menu closed on outside tap):
    // the failure must be spoken, not only visible in the list.
    toggleSpace.mockRejectedValueOnce(new Error('boom'));
    useSpaces.mockReturnValue(hookValue(TWO_SPACES));
    const { user } = renderWithProviders(<ActiveSpacesIndicator />);
    await user.click(screen.getByRole('button'));

    await user.click(await screen.findByRole('menuitemcheckbox', { name: 'Cuisine' }));

    const { toast } = await import('sonner');
    expect(toast.error).toHaveBeenCalled();
  });

  it('disables the switches while a toggle is in flight', async () => {
    useSpaces.mockReturnValue(hookValue(TWO_SPACES, { toggling: true }));
    const { user } = renderWithProviders(<ActiveSpacesIndicator />);
    await user.click(screen.getByRole('button'));

    const item = await screen.findByRole('menuitemcheckbox', { name: 'Droit' });
    expect(item).toHaveAttribute('aria-disabled', 'true');
  });

  it('keeps the management page one item away', async () => {
    useSpaces.mockReturnValue(hookValue(TWO_SPACES));
    const { user } = renderWithProviders(<ActiveSpacesIndicator />);
    await user.click(screen.getByRole('button'));

    const manage = await screen.findByRole('menuitem', { name: /spaces.quick_manage/ });
    expect(manage.getAttribute('href')).toContain('/dashboard/spaces');
  });
});
