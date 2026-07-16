/**
 * ThemeToggle — toggles the next-themes theme and, for an authenticated user,
 * persists it via a PATCH mutation.
 *
 * next-themes is overridden locally (instead of the global passthrough) to
 * capture `setTheme` and pin the resolved theme to 'light'.
 */

import { describe, it, expect, vi, beforeEach } from 'vitest';

import { renderWithProviders, screen, waitFor } from '@/__tests__/test-utils';

const { setTheme } = vi.hoisted(() => ({ setTheme: vi.fn() }));
vi.mock('next-themes', () => ({ useTheme: () => ({ theme: 'light', setTheme }) }));

const { useAuth } = vi.hoisted(() => ({ useAuth: vi.fn() }));
vi.mock('@/hooks/useAuth', () => ({ useAuth }));

const { mutate } = vi.hoisted(() => ({ mutate: vi.fn() }));
vi.mock('@/hooks/useApiMutation', () => ({ useApiMutation: () => ({ mutate }) }));

import { ThemeToggle } from '../theme-toggle';

beforeEach(() => {
  vi.clearAllMocks();
  mutate.mockResolvedValue(undefined);
});

describe('ThemeToggle', () => {
  it('renders the theme toggle control', () => {
    useAuth.mockReturnValue({ user: { id: 'u1' }, refreshUser: vi.fn() });
    renderWithProviders(<ThemeToggle />);
    expect(screen.getByRole('button', { name: 'theme.toggle' })).toBeInTheDocument();
  });

  it('switches light → dark and persists it for an authenticated user', async () => {
    useAuth.mockReturnValue({ user: { id: 'u1' }, refreshUser: vi.fn() });
    const { user } = renderWithProviders(<ThemeToggle />);
    await user.click(screen.getByRole('button', { name: 'theme.toggle' }));
    expect(setTheme).toHaveBeenCalledWith('dark');
    await waitFor(() => expect(mutate).toHaveBeenCalledWith('/users/u1', { theme: 'dark' }));
  });

  it('switches the theme but does not persist when there is no user', async () => {
    useAuth.mockReturnValue({ user: null, refreshUser: vi.fn() });
    const { user } = renderWithProviders(<ThemeToggle />);
    await user.click(screen.getByRole('button', { name: 'theme.toggle' }));
    expect(setTheme).toHaveBeenCalledWith('dark');
    expect(mutate).not.toHaveBeenCalled();
  });
});
