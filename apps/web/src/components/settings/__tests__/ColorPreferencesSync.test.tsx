import { render } from '@testing-library/react';
import { beforeEach, expect, it, vi } from 'vitest';

const { useAuth, setColorTheme, state } = vi.hoisted(() => ({
  useAuth: vi.fn(),
  setColorTheme: vi.fn(),
  state: { colorTheme: 'default' },
}));
vi.mock('@/hooks/useAuth', () => ({ useAuth }));
vi.mock('@/lib/theme-context', () => ({ useColorTheme: () => ({ ...state, setColorTheme }) }));

import { ColorPreferencesSync } from '../ColorPreferencesSync';

beforeEach(() => {
  vi.clearAllMocks();
  state.colorTheme = 'default';
});

it('applies a validated account theme on pages where the selector is absent', () => {
  useAuth.mockReturnValue({ user: { id: 'one', color_theme: 'ocean' } });
  render(<ColorPreferencesSync />);
  expect(setColorTheme).toHaveBeenCalledWith('ocean');
});

it('preserves a local choice until the changed account value arrives', () => {
  useAuth.mockReturnValue({ user: { id: 'one', color_theme: 'default' } });
  const { rerender } = render(<ColorPreferencesSync />);
  state.colorTheme = 'forest';
  rerender(<ColorPreferencesSync />);
  expect(setColorTheme).not.toHaveBeenCalled();
  useAuth.mockReturnValue({ user: { id: 'one', color_theme: 'ocean' } });
  rerender(<ColorPreferencesSync />);
  expect(setColorTheme).toHaveBeenCalledWith('ocean');
});

it('refuses an unsupported persisted colour instead of inventing an attribute', () => {
  useAuth.mockReturnValue({ user: { id: 'one', color_theme: 'arbitrary-attribute' } });
  render(<ColorPreferencesSync />);
  expect(setColorTheme).not.toHaveBeenCalled();
});
