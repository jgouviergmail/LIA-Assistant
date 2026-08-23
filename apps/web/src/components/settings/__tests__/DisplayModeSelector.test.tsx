/**
 * DisplayModeSelector — the four-way display choice in Settings › Appearance.
 *
 * It exists because the header's circular toggle drops `system`, which is the
 * `users.theme` column's `server_default` and therefore where every account
 * starts. Without this panel one press of the header toggle would lose it for
 * good.
 *
 * The subtle rule under test: OLED is offered only under an EXPLICIT dark mode.
 * `users.theme` encodes `'oled'` as "dark, with OLED", so `system + OLED` has
 * nowhere to be stored — enabling it from `system` would have to silently pin
 * the user to dark.
 */

import { describe, it, expect, vi, beforeEach } from 'vitest';

import { renderWithProviders, screen } from '@/__tests__/test-utils';

const { apply, modeState } = vi.hoisted(() => ({
  apply: vi.fn(),
  modeState: { mounted: true, mode: 'light', resolved: 'light', oled: false },
}));
vi.mock('@/hooks/useThemeMode', () => ({
  useThemeMode: () => ({ ...modeState, apply }),
}));

import { DisplayModeSelector } from '../DisplayModeSelector';

function setMode(mode: string, oled = false, mounted = true) {
  modeState.mode = mode;
  modeState.resolved = mode === 'dark' ? 'dark' : 'light';
  modeState.oled = oled;
  modeState.mounted = mounted;
}

beforeEach(() => {
  vi.clearAllMocks();
  setMode('light');
});

describe('DisplayModeSelector — mode choice', () => {
  it('offers the three modes as a real radio group', () => {
    renderWithProviders(<DisplayModeSelector lng="fr" />);
    const radios = screen.getAllByRole('radio');
    expect(radios).toHaveLength(3);
    // Native radios: the browser supplies arrow-key navigation and roving
    // focus, so no keyboard handler of ours can be missing or wrong.
    expect(radios.every(r => r.getAttribute('name') === 'display-mode')).toBe(true);
  });

  it('marks the active mode as checked', () => {
    setMode('dark');
    renderWithProviders(<DisplayModeSelector lng="fr" />);
    expect(screen.getByRole('radio', { name: /settings.theme.dark/ })).toBeChecked();
  });

  it('reaches system, which the header cycle cannot', async () => {
    const { user } = renderWithProviders(<DisplayModeSelector lng="fr" />);
    await user.click(screen.getByRole('radio', { name: /settings.theme.system/ }));
    expect(apply).toHaveBeenCalledWith({ mode: 'system', oled: false });
  });

  it('drops OLED when leaving dark, since no other mode can render it', async () => {
    setMode('dark', true);
    const { user } = renderWithProviders(<DisplayModeSelector lng="fr" />);
    await user.click(screen.getByRole('radio', { name: /settings.theme.light/ }));
    expect(apply).toHaveBeenCalledWith({ mode: 'light', oled: false });
  });

  it('keeps OLED when re-selecting dark', async () => {
    setMode('light', true);
    const { user } = renderWithProviders(<DisplayModeSelector lng="fr" />);
    await user.click(screen.getByRole('radio', { name: /settings.theme.dark/ }));
    expect(apply).toHaveBeenCalledWith({ mode: 'dark', oled: true });
  });
});

describe('DisplayModeSelector — OLED', () => {
  it('is disabled outside an explicit dark mode', () => {
    renderWithProviders(<DisplayModeSelector lng="fr" />);
    expect(screen.getByRole('switch')).toBeDisabled();
  });

  it('stays disabled under system even when the OS resolves to dark', () => {
    // The trap: `resolved` is dark, but the stored value would have to be
    // 'oled', which means dark — silently overwriting the user's 'system'.
    modeState.mode = 'system';
    modeState.resolved = 'dark';
    renderWithProviders(<DisplayModeSelector lng="fr" />);
    expect(screen.getByRole('switch')).toBeDisabled();
  });

  it('explains why it is unavailable rather than just greying out', () => {
    renderWithProviders(<DisplayModeSelector lng="fr" />);
    expect(screen.getByText('settings.theme.oled_requires_dark')).toBeInTheDocument();
  });

  it('becomes available under dark and describes what it does', () => {
    setMode('dark');
    renderWithProviders(<DisplayModeSelector lng="fr" />);
    expect(screen.getByRole('switch')).toBeEnabled();
    expect(screen.getByText('settings.theme.oled_description')).toBeInTheDocument();
  });

  it('turns OLED on without changing the mode', async () => {
    setMode('dark');
    const { user } = renderWithProviders(<DisplayModeSelector lng="fr" />);
    await user.click(screen.getByRole('switch'));
    expect(apply).toHaveBeenCalledWith({ mode: 'dark', oled: true });
  });

  it('turns OLED back off', async () => {
    setMode('dark', true);
    const { user } = renderWithProviders(<DisplayModeSelector lng="fr" />);
    expect(screen.getByRole('switch')).toBeChecked();
    await user.click(screen.getByRole('switch'));
    expect(apply).toHaveBeenCalledWith({ mode: 'dark', oled: false });
  });

  it('never shows itself as on while it is unavailable', () => {
    // A stored flag from a previous dark session must not display as active
    // under light — the page would plainly not be black.
    setMode('light', true);
    renderWithProviders(<DisplayModeSelector lng="fr" />);
    expect(screen.getByRole('switch')).not.toBeChecked();
  });

  it('carries an accessible name', () => {
    setMode('dark');
    renderWithProviders(<DisplayModeSelector lng="fr" />);
    expect(screen.getByRole('switch')).toHaveAccessibleName('settings.theme.oled');
  });
});

describe('DisplayModeSelector — hydration', () => {
  it('renders a placeholder rather than a wrong state before mount', () => {
    setMode('light', false, false);
    renderWithProviders(<DisplayModeSelector lng="fr" />);
    expect(screen.queryAllByRole('radio')).toHaveLength(0);
    expect(screen.queryByRole('switch')).toBeNull();
  });
});
