/**
 * ThemeToggle — the circular light → dark → OLED → light control.
 *
 * `next-themes` is overridden locally (instead of the global passthrough) so
 * the test can drive `resolvedTheme` and capture `setTheme`. The local mock now
 * exposes `resolvedTheme` because the cycle reads it rather than `theme`: every
 * account starts on `system` (the column's `server_default`), which a
 * `theme === 'dark'` test misclassifies as "not dark", so a user on a dark OS
 * used to click and see nothing happen.
 */

import { describe, it, expect, vi, beforeEach } from 'vitest';

import { renderWithProviders, screen, waitFor } from '@/__tests__/test-utils';
import { OLED_STORAGE_KEY } from '@/lib/theme-mode';

const { setTheme, themeState } = vi.hoisted(() => ({
  setTheme: vi.fn(),
  themeState: { resolvedTheme: 'light' as string | undefined, theme: 'light' as string },
}));
vi.mock('next-themes', () => ({
  useTheme: () => ({ ...themeState, setTheme }),
}));

const { useAuth } = vi.hoisted(() => ({ useAuth: vi.fn() }));
vi.mock('@/hooks/useAuth', () => ({ useAuth }));

const { mutate } = vi.hoisted(() => ({ mutate: vi.fn() }));
vi.mock('@/hooks/useApiMutation', () => ({ useApiMutation: () => ({ mutate }) }));

import { ThemeToggle } from '../theme-toggle';

/** Put the control in a known state before each case. */
function setEnvironment(resolved: string | undefined, oled: boolean, theme = resolved ?? 'light') {
  themeState.resolvedTheme = resolved;
  themeState.theme = theme;
  window.localStorage.setItem(OLED_STORAGE_KEY, oled ? '1' : '0');
  if (oled) document.documentElement.setAttribute('data-oled', '');
  else document.documentElement.removeAttribute('data-oled');
}

beforeEach(() => {
  vi.clearAllMocks();
  mutate.mockResolvedValue(undefined);
  useAuth.mockReturnValue({ user: { id: 'u1' }, refreshUser: vi.fn() });
  setEnvironment('light', false);
});

describe('ThemeToggle — the cycle', () => {
  it('renders a named control', () => {
    renderWithProviders(<ThemeToggle />);
    expect(screen.getByRole('button')).toBeInTheDocument();
  });

  it('light → dark', async () => {
    const { user } = renderWithProviders(<ThemeToggle />);
    await user.click(screen.getByRole('button'));
    expect(setTheme).toHaveBeenCalledWith('dark');
    expect(document.documentElement.hasAttribute('data-oled')).toBe(false);
  });

  it('dark → OLED sets the attribute and does NOT change the next-themes theme', async () => {
    setEnvironment('dark', false);
    const { user } = renderWithProviders(<ThemeToggle />);
    await user.click(screen.getByRole('button'));
    // Staying on 'dark' is the whole design: `.dark` must remain on <html> so
    // the 9 `resolvedTheme === 'dark'` sites and the `html:not(.dark) .cosmos`
    // rules keep their dark branch.
    expect(setTheme).toHaveBeenCalledWith('dark');
    expect(document.documentElement.hasAttribute('data-oled')).toBe(true);
  });

  it('OLED → light clears the attribute', async () => {
    setEnvironment('dark', true);
    const { user } = renderWithProviders(<ThemeToggle />);
    await user.click(screen.getByRole('button'));
    expect(setTheme).toHaveBeenCalledWith('light');
    expect(document.documentElement.hasAttribute('data-oled')).toBe(false);
  });

  it('advances visibly for a user left on system with a dark OS', async () => {
    setEnvironment('dark', false, 'system');
    const { user } = renderWithProviders(<ThemeToggle />);
    await user.click(screen.getByRole('button'));
    expect(document.documentElement.hasAttribute('data-oled')).toBe(true);
  });

  // A fresh mount per step, deliberately: the OLED flag is hydrated from
  // storage ONCE, in a mount effect, so rerendering the same instance would
  // never pick up a storage change — the component would look broken while
  // behaving exactly as designed.
  it.each([
    ['light', false, 'lucide-moon'],
    ['dark', false, 'lucide-eclipse'],
    ['dark', true, 'lucide-sun'],
  ] as const)('from %s (oled=%s) it offers %s', (resolved, oledOn, icon) => {
    setEnvironment(resolved, oledOn);
    const { container } = renderWithProviders(<ThemeToggle />);
    expect(container.querySelector('svg')?.getAttribute('class')).toContain(icon);
  });

  it('names itself after what pressing it will do', () => {
    renderWithProviders(<ThemeToggle />);
    expect(screen.getByRole('button')).toHaveAccessibleName('theme.to_dark');
  });
});

describe('ThemeToggle — persistence', () => {
  it('persists OLED as its own theme value', async () => {
    setEnvironment('dark', false);
    const { user } = renderWithProviders(<ThemeToggle />);
    await user.click(screen.getByRole('button'));
    await waitFor(() => expect(mutate).toHaveBeenCalledWith('/users/u1', { theme: 'oled' }));
  });

  it('persists the plain modes unchanged', async () => {
    const { user } = renderWithProviders(<ThemeToggle />);
    await user.click(screen.getByRole('button'));
    await waitFor(() => expect(mutate).toHaveBeenCalledWith('/users/u1', { theme: 'dark' }));
  });

  it('mirrors the flag into localStorage so the anti-FOUC script can read it', async () => {
    setEnvironment('dark', false);
    const { user } = renderWithProviders(<ThemeToggle />);
    await user.click(screen.getByRole('button'));
    expect(window.localStorage.getItem(OLED_STORAGE_KEY)).toBe('1');
  });

  it('switches the theme but does not persist when there is no user', async () => {
    useAuth.mockReturnValue({ user: null, refreshUser: vi.fn() });
    const { user } = renderWithProviders(<ThemeToggle />);
    await user.click(screen.getByRole('button'));
    expect(setTheme).toHaveBeenCalledWith('dark');
    expect(mutate).not.toHaveBeenCalled();
  });

  it('restores a stored OLED preference from the user record', async () => {
    setEnvironment('dark', false);
    useAuth.mockReturnValue({ user: { id: 'u1', theme: 'oled' }, refreshUser: vi.fn() });
    renderWithProviders(<ThemeToggle />);
    await waitFor(() => expect(document.documentElement.hasAttribute('data-oled')).toBe(true));
  });

  it('does not fight the provider when the user record says system', async () => {
    useAuth.mockReturnValue({ user: { id: 'u1', theme: 'system' }, refreshUser: vi.fn() });
    renderWithProviders(<ThemeToggle />);
    await waitFor(() => expect(setTheme).not.toHaveBeenCalled());
  });
});
