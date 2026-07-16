/**
 * ThemeSelector — the five colour-theme choices, selecting one (local state +
 * persistence for an authenticated user), and the no-user path.
 *
 * `@/lib/theme-context` is mocked so `setColorTheme` is observable; rendered with
 * `collapsible={false}` to bypass the SettingsSection accordion wrapper.
 */

import { describe, it, expect, vi, beforeEach } from 'vitest';

import { renderWithProviders, screen, waitFor } from '@/__tests__/test-utils';

const { setColorTheme } = vi.hoisted(() => ({ setColorTheme: vi.fn() }));
vi.mock('@/lib/theme-context', () => ({
  ColorThemeProvider: ({ children }: { children: React.ReactNode }) => children,
  useColorTheme: () => ({ colorTheme: 'default', setColorTheme }),
}));

const { useAuth } = vi.hoisted(() => ({ useAuth: vi.fn() }));
vi.mock('@/hooks/useAuth', () => ({ useAuth }));

const { mutate } = vi.hoisted(() => ({ mutate: vi.fn() }));
vi.mock('@/hooks/useApiMutation', () => ({ useApiMutation: () => ({ mutate }) }));

import { ThemeSelector } from '../theme-selector';

beforeEach(() => {
  vi.clearAllMocks();
  mutate.mockResolvedValue(undefined);
});

describe('ThemeSelector', () => {
  it('renders every colour theme as a selectable option', () => {
    useAuth.mockReturnValue({ user: { id: 'u1' }, refreshUser: vi.fn() });
    renderWithProviders(<ThemeSelector lng="en" collapsible={false} />);
    for (const name of ['default', 'ocean', 'forest', 'sunset', 'slate']) {
      expect(
        screen.getByRole('button', { name: `settings.theme.themes.${name}.label` })
      ).toBeInTheDocument();
    }
  });

  it('selecting a theme updates local state and persists it for an authenticated user', async () => {
    useAuth.mockReturnValue({ user: { id: 'u1' }, refreshUser: vi.fn() });
    const { user } = renderWithProviders(<ThemeSelector lng="en" collapsible={false} />);
    await user.click(screen.getByRole('button', { name: 'settings.theme.themes.ocean.label' }));
    expect(setColorTheme).toHaveBeenCalledWith('ocean');
    await waitFor(() => expect(mutate).toHaveBeenCalledWith('/users/u1', { color_theme: 'ocean' }));
  });

  it('selecting a theme updates local state but does not persist without a user', async () => {
    useAuth.mockReturnValue({ user: null, refreshUser: vi.fn() });
    const { user } = renderWithProviders(<ThemeSelector lng="en" collapsible={false} />);
    await user.click(screen.getByRole('button', { name: 'settings.theme.themes.forest.label' }));
    expect(setColorTheme).toHaveBeenCalledWith('forest');
    expect(mutate).not.toHaveBeenCalled();
  });
});
