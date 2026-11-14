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
  sandboxEgressEnabled: true,
  liveEnabled: true,
  radioEnabled: true,
  channelsEnabled: true,
  psycheEnabled: true,
  journalsEnabled: true,
  skillsEnabled: true,
  mcpEnabled: true,
  ragSpacesEnabled: true,
  imageGenerationEnabled: true,
  telephonyEnabled: true,
  hapticsSupported: true,
  debugUserAccess: true,
};

/**
 * What the operator closed, as each reading knows it: the page's own read of
 * `/config` (what the picker LISTS) and the layout's (what the dock draws, and
 * what the picker COUNTS). They agree, except between a switch and a reload.
 */
const closed = vi.hoisted(() => ({ page: [] as string[], layout: [] as string[] }));
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
vi.mock('@/hooks/useSettingsAvailability', () => {
  const without = (flags: string[]) => ({
    ...AVAILABILITY,
    ...Object.fromEntries(flags.map(flag => [flag, false])),
  });
  return {
    useSettingsAvailability: () => without(closed.page),
    usePassiveSettingsAvailability: () => without(closed.layout),
  };
});
// The counter is the one text that carries numbers: show them.
vi.mock('@/i18n/client', () => ({
  useTranslation: () => ({
    t: (key: string, values?: Record<string, unknown>) =>
      values ? `${key} ${JSON.stringify(values)}` : key,
    i18n: { language: 'fr', changeLanguage: vi.fn() },
  }),
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
  closed.page = [];
  closed.layout = [];
  save.mockResolvedValue(true);
});

const COUNT = (current: number, max: number) =>
  `settings.my_shortcuts.count ${JSON.stringify({ current, max })}`;

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

describe('MyShortcutsSettings — a pinned section the account cannot open now', () => {
  /** The journals, pinned, then switched off by the operator. */
  const closeJournals = () => {
    closed.page = ['journalsEnabled'];
    closed.layout = ['journalsEnabled'];
  };
  const journalsBox = () =>
    screen.queryByRole('checkbox', { name: SETTINGS_SEARCH_META.journals.titleKey });

  it('lists no box for it and counts what the dock draws', () => {
    state.shortcuts = ['theme', 'journals', 'font'];
    closeJournals();
    render(<MyShortcutsSettings lng="fr" />);

    expect(journalsBox()).toBeNull();
    expect(screen.getAllByRole('checkbox', { checked: true })).toHaveLength(2);
    expect(screen.getByText(COUNT(2, 5))).toBeInTheDocument();
  });

  it('counts by the layout, like the dock, where the page has a fresher answer', () => {
    // The operator switched the journals back on since this page loaded its
    // layout: the list already offers the box, the dock draws nothing yet —
    // and the counter says what the dock shows until the next load.
    state.shortcuts = ['theme', 'journals', 'font'];
    closed.layout = ['journalsEnabled'];
    render(<MyShortcutsSettings lng="fr" />);

    expect(journalsBox()).toBeChecked();
    expect(screen.getByText(COUNT(2, 5))).toBeInTheDocument();
  });

  it('is not at the cap for a pin nobody can see: the next box is takeable', async () => {
    state.shortcuts = ['theme', 'journals', 'font'];
    state.maxCount = 3;
    closeJournals();
    render(<MyShortcutsSettings lng="fr" />);

    const next = box('language');
    expect(next).not.toHaveAttribute('aria-disabled');
    expect(screen.queryByText('settings.my_shortcuts.limit_reached')).toBeNull();
    fireEvent.click(next);

    // The hidden pin gives its place: the list the API accepts holds the choice.
    await waitFor(() => expect(save).toHaveBeenCalledWith(['theme', 'font', 'language']));
  });

  it('keeps the hidden pin while there is room, so that it comes back with its capability', async () => {
    state.shortcuts = ['theme', 'journals'];
    closeJournals();
    render(<MyShortcutsSettings lng="fr" />);

    fireEvent.click(box('font'));

    await waitFor(() => expect(save).toHaveBeenCalledWith(['theme', 'journals', 'font']));
  });

  it('is at the cap once what the dock draws fills it', () => {
    state.shortcuts = ['theme', 'journals', 'font'];
    state.maxCount = 2;
    closeJournals();
    render(<MyShortcutsSettings lng="fr" />);

    expect(box('language')).toHaveAttribute('aria-disabled', 'true');
    expect(screen.getByText('settings.my_shortcuts.limit_reached')).toBeInTheDocument();
    expect(screen.getByText(COUNT(2, 2))).toBeInTheDocument();
  });

  it('says nothing is pinned when the only pin cannot be opened', () => {
    state.shortcuts = ['journals'];
    closeJournals();
    render(<MyShortcutsSettings lng="fr" />);

    expect(screen.getByText('settings.my_shortcuts.empty')).toBeInTheDocument();
    expect(screen.getByText(COUNT(0, 5))).toBeInTheDocument();
  });
});
