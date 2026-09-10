/**
 * MyShortcutsSettings (ADR-277) — the picker offers what the shell shows,
 * pins and unpins with the whole list, and marks the cap without dropping a
 * keyboard reader's focus.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';

import { SETTINGS_SEARCH_META, type SettingsSearchAvailability } from '@/lib/settings-search';
import type { SettingsSectionToken } from '@/lib/settings-sections';
import { buildSettingsShellModel } from '@/lib/settings-shell-model';

const AVAILABILITY: SettingsSearchAvailability = {
  isSuperuser: false,
  openLoopsEnabled: true,
  habitsEnabled: true,
  peersEnabled: true,
  debugUserAccess: true,
};

const state = vi.hoisted(() => ({ shortcuts: [] as string[], maxCount: 5 }));
const save = vi.hoisted(() => vi.fn(async (_next: string[]) => true));
const toastError = vi.hoisted(() => vi.fn());

vi.mock('sonner', () => ({ toast: { error: toastError, success: vi.fn() } }));
vi.mock('@/hooks/useSettingsShortcuts', async importOriginal => {
  const original = await importOriginal<typeof import('@/hooks/useSettingsShortcuts')>();
  return {
    ...original,
    useSettingsShortcuts: () => ({
      shortcuts: state.shortcuts,
      maxCount: state.maxCount,
      loading: false,
      error: false,
      save,
      saving: false,
    }),
  };
});
vi.mock('@/hooks/useSettingsAvailability', () => ({
  useSettingsAvailability: () => AVAILABILITY,
}));

import { MyShortcutsSettings } from '@/components/settings/MyShortcutsSettings';

/** Every token the shell would list for this account, the picker's own excluded. */
const OFFERED = buildSettingsShellModel(AVAILABILITY)
  .flatMap(tab => tab.groups.flatMap(group => group.sections.map(section => section.token)))
  .filter(token => token !== 'my-shortcuts');

const box = (token: SettingsSectionToken) =>
  screen.getByRole('checkbox', { name: SETTINGS_SEARCH_META[token].titleKey });

beforeEach(() => {
  vi.clearAllMocks();
  state.shortcuts = [];
  state.maxCount = 5;
  save.mockResolvedValue(true);
});

describe('MyShortcutsSettings', () => {
  it('offers every section this account can open, except itself', () => {
    render(<MyShortcutsSettings lng="fr" />);

    expect(screen.getAllByRole('checkbox')).toHaveLength(OFFERED.length);
    expect(
      screen.queryByRole('checkbox', { name: SETTINGS_SEARCH_META['my-shortcuts'].titleKey })
    ).toBeNull();
    // Grouped as the rail groups it, so the reader finds the map they know.
    expect(screen.getByText('settings.groups.personalization')).toBeInTheDocument();
  });

  it('shows the pinned ones checked', () => {
    state.shortcuts = ['theme'];
    render(<MyShortcutsSettings lng="fr" />);

    expect(box('theme')).toBeChecked();
    expect(box('font')).not.toBeChecked();
  });

  it('pins on a click, with the whole list', async () => {
    state.shortcuts = ['theme'];
    render(<MyShortcutsSettings lng="fr" />);

    fireEvent.click(box('font'));

    await waitFor(() => expect(save).toHaveBeenCalledWith(['theme', 'font']));
  });

  it('unpins on a click', async () => {
    state.shortcuts = ['theme', 'font'];
    render(<MyShortcutsSettings lng="fr" />);

    fireEvent.click(box('theme'));

    await waitFor(() => expect(save).toHaveBeenCalledWith(['font']));
  });

  it('at the cap, marks an unpinned box and refuses it without disabling it', () => {
    state.shortcuts = OFFERED.slice(0, 5);
    render(<MyShortcutsSettings lng="fr" />);

    const blocked = box(OFFERED[5]);
    expect(blocked).toHaveAttribute('aria-disabled', 'true');
    expect(blocked).not.toBeDisabled();
    expect(box(OFFERED[0])).not.toHaveAttribute('aria-disabled');
    expect(screen.getByText('settings.my_shortcuts.limit_reached')).toBeInTheDocument();

    fireEvent.click(blocked);

    expect(save).not.toHaveBeenCalled();
  });

  it('still lets a pinned one go at the cap', async () => {
    state.shortcuts = OFFERED.slice(0, 5);
    render(<MyShortcutsSettings lng="fr" />);

    fireEvent.click(box(OFFERED[0]));

    await waitFor(() => expect(save).toHaveBeenCalledWith(OFFERED.slice(1, 5)));
  });

  it('says so when a save is refused', async () => {
    save.mockResolvedValueOnce(false);
    render(<MyShortcutsSettings lng="fr" />);

    fireEvent.click(box('theme'));

    await waitFor(() => expect(toastError).toHaveBeenCalledWith('common.error'));
  });

  it('says that nothing is pinned yet, and counts once the cap is known', () => {
    render(<MyShortcutsSettings lng="fr" />);

    expect(screen.getByText('settings.my_shortcuts.empty')).toBeInTheDocument();
    expect(screen.getByText(/settings\.my_shortcuts\.count/)).toBeInTheDocument();
  });
});
