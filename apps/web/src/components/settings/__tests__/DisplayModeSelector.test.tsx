/**
 * DisplayModeSelector — the four-way display choice in Settings › Appearance.
 *
 * It exists because the header's circular toggle drops `system`, which is the
 * `users.theme` column's `server_default` and therefore where every account
 * starts. Without this panel one press of the header toggle would lose it for
 * good.
 *
 * Absolute black is a fourth radio and commits dark + OLED atomically.
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
  it('offers the four modes as a real radio group', () => {
    renderWithProviders(<DisplayModeSelector lng="fr" />);
    const radios = screen.getAllByRole('radio');
    expect(radios).toHaveLength(4);
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

  it('selecting dark explicitly drops OLED', async () => {
    setMode('light', true);
    const { user } = renderWithProviders(<DisplayModeSelector lng="fr" />);
    await user.click(screen.getByRole('radio', { name: /settings.theme.dark/ }));
    expect(apply).toHaveBeenCalledWith({ mode: 'dark', oled: false });
  });
});

describe('DisplayModeSelector — OLED', () => {
  it('offers absolute black directly without a separate switch', async () => {
    const { user } = renderWithProviders(<DisplayModeSelector lng="fr" />);
    expect(screen.queryByRole('switch')).toBeNull();
    await user.click(screen.getByRole('radio', { name: 'settings.theme.oled' }));
    expect(apply).toHaveBeenCalledWith({ mode: 'dark', oled: true });
  });

  it('marks only absolute black when the stored preference is OLED', () => {
    setMode('dark', true);
    renderWithProviders(<DisplayModeSelector lng="fr" />);
    expect(screen.getByRole('radio', { name: 'settings.theme.oled' })).toBeChecked();
    expect(screen.getByRole('radio', { name: 'settings.theme.dark' })).not.toBeChecked();
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
