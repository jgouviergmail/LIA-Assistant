/**
 * SettingsSearch — the combobox contract.
 *
 * The matching itself is pinned in `lib/__tests__/settings-search.test.ts`
 * against the six real dictionaries. What can only be checked here is the
 * INTERACTION: that the field is a real ARIA combobox, that a keyboard reaches
 * every result and picks one, that dismissing behaves the way APG describes,
 * that the count is announced rather than merely displayed, and that a superuser
 * is told the Administration tab is out of scope.
 *
 * The global i18n stub echoes keys, so a section renders as
 * `settings.voice_mode.title`. That is enough — and deliberately so: this file
 * must not become a second, weaker test of the wording.
 */

import { describe, expect, it, vi } from 'vitest';

import { renderWithProviders, screen, within } from '@/__tests__/test-utils';
import type { SettingsSearchAvailability } from '@/lib/settings-search';

import { SettingsSearch } from '../SettingsSearch';

/** Stable identity: the component memoizes its index on this object. */
const AVAILABLE: SettingsSearchAvailability = {
  isSuperuser: false,
  openLoopsEnabled: true,
  habitsEnabled: true,
  peersEnabled: true,
  debugUserAccess: true,
};

function renderSearch(overrides: Partial<SettingsSearchAvailability> = {}) {
  const onSelect = vi.fn();
  const availability = { ...AVAILABLE, ...overrides };
  const view = renderWithProviders(
    <SettingsSearch lng="en" availability={availability} onSelect={onSelect} />
  );
  return { ...view, onSelect };
}

const box = () => screen.getByRole('combobox');

describe('SettingsSearch — ARIA shape', () => {
  it('exposes a labelled, collapsed combobox with no popup', () => {
    renderSearch();
    const input = box();
    expect(input).toHaveAccessibleName('settings.search.label');
    expect(input).toHaveAttribute('aria-expanded', 'false');
    expect(input).toHaveAttribute('aria-autocomplete', 'list');
    expect(screen.queryByRole('listbox')).not.toBeInTheDocument();
  });

  it('stays collapsed on focus alone — an empty query is not a search', async () => {
    const { user } = renderSearch();
    await user.click(box());
    expect(box()).toHaveAttribute('aria-expanded', 'false');
    expect(screen.queryByRole('listbox')).not.toBeInTheDocument();
  });

  it('opens a listbox of options once a query is typed', async () => {
    const { user } = renderSearch();
    await user.type(box(), 'voice_mode');

    const listbox = screen.getByRole('listbox');
    expect(box()).toHaveAttribute('aria-expanded', 'true');
    expect(box()).toHaveAttribute('aria-controls', listbox.id);
    expect(listbox).toHaveAccessibleName('settings.search.results_label');

    const options = within(listbox).getAllByRole('option');
    expect(options).toHaveLength(1);
    expect(options[0]).toHaveTextContent('settings.voice_mode.title');
  });

  it('shows the tab and the group of each result', async () => {
    const { user } = renderSearch();
    await user.type(box(), 'voice_mode');
    const option = screen.getByRole('option');
    // A title alone is ambiguous: "Debug Panel" exists in two tabs.
    expect(option).toHaveTextContent('settings.tabs.preferences');
    expect(option).toHaveTextContent('settings.groups.voice_media');
  });
});

describe('SettingsSearch — keyboard', () => {
  it('walks the options with the arrow keys and wraps around', async () => {
    const { user } = renderSearch();
    await user.type(box(), 'settings.security');
    const options = screen.getAllByRole('option');
    expect(options.length).toBeGreaterThan(1);

    expect(box()).not.toHaveAttribute('aria-activedescendant');

    await user.keyboard('{ArrowDown}');
    expect(box()).toHaveAttribute('aria-activedescendant', options[0].id);
    expect(screen.getAllByRole('option')[0]).toHaveAttribute('aria-selected', 'true');

    await user.keyboard('{ArrowUp}');
    // Wraps to the last rather than escaping the list.
    expect(box()).toHaveAttribute(
      'aria-activedescendant',
      screen.getAllByRole('option').at(-1)!.id
    );

    await user.keyboard('{ArrowDown}');
    expect(box()).toHaveAttribute('aria-activedescendant', screen.getAllByRole('option')[0].id);
  });

  it('keeps the walked-to option in view', async () => {
    // `aria-activedescendant` does not move focus, so the browser scrolls
    // nothing on its own: without this the arrow key would walk past the
    // bottom of a scrolling listbox onto options the reader cannot see.
    const scrollIntoView = vi.fn();
    const original = Element.prototype.scrollIntoView;
    Element.prototype.scrollIntoView = scrollIntoView;
    try {
      const { user } = renderSearch();
      await user.type(box(), 'settings.security');
      await user.keyboard('{ArrowDown}{ArrowDown}');
      expect(scrollIntoView).toHaveBeenCalled();
      expect(scrollIntoView.mock.calls.at(-1)?.[0]).toEqual({ block: 'nearest' });
    } finally {
      Element.prototype.scrollIntoView = original;
    }
  });

  it('picks the active option with Enter and clears the field', async () => {
    const { user, onSelect } = renderSearch();
    await user.type(box(), 'voice_mode');
    await user.keyboard('{ArrowDown}{Enter}');

    expect(onSelect).toHaveBeenCalledTimes(1);
    expect(onSelect.mock.calls[0][0]).toMatchObject({
      token: 'voice-mode',
      target: { tab: 'preferences', accordionValue: 'voice-mode' },
    });
    // Cleared: the page takes focus from here, and a stale query would reopen
    // the popup the next time the field is focused.
    expect(box()).toHaveValue('');
    expect(screen.queryByRole('listbox')).not.toBeInTheDocument();
  });

  it('ignores Enter while no option is active', async () => {
    const { user, onSelect } = renderSearch();
    await user.type(box(), 'voice_mode');
    await user.keyboard('{Enter}');
    expect(onSelect).not.toHaveBeenCalled();
  });

  it('dismisses with Escape, then clears with a second Escape', async () => {
    const { user } = renderSearch();
    await user.type(box(), 'voice_mode');
    expect(screen.getByRole('listbox')).toBeInTheDocument();

    await user.keyboard('{Escape}');
    expect(screen.queryByRole('listbox')).not.toBeInTheDocument();
    expect(box()).toHaveValue('voice_mode');

    await user.keyboard('{Escape}');
    expect(box()).toHaveValue('');
  });
});

describe('SettingsSearch — pointer', () => {
  it('selects an option on click', async () => {
    const { user, onSelect } = renderSearch();
    await user.type(box(), 'voice_mode');
    await user.click(screen.getByRole('option'));
    expect(onSelect.mock.calls[0][0]).toMatchObject({ token: 'voice-mode' });
  });

  it('closes when the pointer goes elsewhere', async () => {
    const { user } = renderSearch();
    await user.type(box(), 'voice_mode');
    await user.click(document.body);
    expect(screen.queryByRole('listbox')).not.toBeInTheDocument();
  });

  it('clears and returns focus to the field', async () => {
    const { user } = renderSearch();
    await user.type(box(), 'voice_mode');
    await user.click(screen.getByRole('button', { name: 'settings.search.clear' }));
    expect(box()).toHaveValue('');
    expect(box()).toHaveFocus();
  });

  it('offers no clear button while the field is empty', () => {
    renderSearch();
    expect(screen.queryByRole('button', { name: 'settings.search.clear' })).not.toBeInTheDocument();
  });
});

describe('SettingsSearch — telling the truth about the result set', () => {
  it('announces the number of matches without taking any vertical space', async () => {
    const { user } = renderSearch();
    await user.type(box(), 'voice_mode');
    // A live region, not a visible line: the field sits in the sticky bar whose
    // height `SettingsSection`'s scroll-margin is calibrated against.
    const status = screen.getByRole('status');
    expect(status).toHaveTextContent('settings.search.results_count');
    expect(status).toHaveClass('sr-only');
  });

  it('says so explicitly when nothing matches, and offers no listbox', async () => {
    const { user } = renderSearch();
    await user.type(box(), 'zzzqwerty');
    expect(screen.queryByRole('listbox')).not.toBeInTheDocument();
    // Two elements legitimately carry the same sentence — the visible message
    // and the live region — so the selector says which one is meant rather than
    // the assertion being loosened to "somewhere on the page".
    expect(screen.getByText('settings.search.no_results', { selector: 'p' })).toBeVisible();
    expect(screen.getByText('settings.search.no_results_hint')).toBeInTheDocument();
    expect(screen.getByRole('status')).toHaveTextContent('settings.search.no_results');
  });

  it('tells a superuser that the administration tab is out of scope', async () => {
    const { user } = renderSearch({ isSuperuser: true });
    await user.type(box(), 'voice_mode');
    expect(screen.getByText('settings.search.admin_not_indexed')).toBeInTheDocument();
  });

  it('stays silent about it for a regular user, who has no such tab', async () => {
    const { user } = renderSearch();
    await user.type(box(), 'voice_mode');
    expect(screen.queryByText('settings.search.admin_not_indexed')).not.toBeInTheDocument();
  });

  it('never offers a section the instance has switched off', async () => {
    const { user } = renderSearch({ openLoopsEnabled: false });
    await user.type(box(), 'open_loops');
    expect(screen.queryByRole('listbox')).not.toBeInTheDocument();
    expect(screen.getByText('settings.search.no_results', { selector: 'p' })).toBeVisible();
  });

  it('offers it again when the instance has it on', async () => {
    const { user } = renderSearch({ openLoopsEnabled: true });
    await user.type(box(), 'open_loops');
    expect(screen.getByRole('option')).toHaveTextContent('settings.open_loops.title');
  });
});

describe('SettingsSearch — explaining a match', () => {
  it('highlights the matched characters', async () => {
    const { user } = renderSearch();
    await user.type(box(), 'voice_mode');
    const marks = screen.getByRole('option').querySelectorAll('mark');
    expect(marks.length).toBeGreaterThan(0);
    expect(marks[0]).toHaveTextContent('voice_mode');
  });

  it('adds the description line only when the title is not what matched', async () => {
    const { user } = renderSearch();
    // `settings.search.keywords.psyche` is a keyword-tier hit: the title
    // (`psyche.title`) does not contain "keywords".
    await user.type(box(), 'keywords.psyche');
    const option = screen.getByRole('option');
    expect(option).toHaveTextContent('psyche.description');

    await user.clear(box());
    await user.type(box(), 'psyche.title');
    expect(screen.getByRole('option')).not.toHaveTextContent('psyche.description');
  });
});
