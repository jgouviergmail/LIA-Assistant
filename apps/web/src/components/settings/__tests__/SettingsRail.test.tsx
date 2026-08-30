/**
 * SettingsRail — the master-detail navigation.
 *
 * A `<nav>` of real buttons: every visible section reachable in one
 * activation, the active one stated with `aria-current`, tabs and groups as
 * visual structure. What the rail SHOWS is the shell model's business (tested
 * in `settings-shell-model.test.ts`); here we hold the interaction contract
 * and that the rail renders what the model says — admin entries included for a
 * superuser, excluded otherwise.
 */

import { describe, expect, it, vi } from 'vitest';

import { renderWithProviders, screen, within } from '@/__tests__/test-utils';
import { SETTINGS_GROUP_TONES } from '@/lib/settings-group-tones';
import { buildSettingsShellModel } from '@/lib/settings-shell-model';
import { SETTINGS_SEARCH_META } from '@/lib/settings-search';
import type { SettingsSearchAvailability } from '@/lib/settings-search';
import type { SettingsSectionToken } from '@/lib/settings-sections';

import { SettingsRail } from '../SettingsRail';

const AVAILABLE: SettingsSearchAvailability = {
  isSuperuser: false,
  openLoopsEnabled: true,
  habitsEnabled: true,
  peersEnabled: true,
  debugUserAccess: true,
};

function renderRail({
  availability = AVAILABLE,
  activeToken = null as SettingsSectionToken | null,
} = {}) {
  const onSelect = vi.fn();
  const model = buildSettingsShellModel(availability);
  const view = renderWithProviders(
    <SettingsRail lng="en" model={model} activeToken={activeToken} onSelect={onSelect} />
  );
  return { ...view, onSelect };
}

describe('SettingsRail', () => {
  it('is a labelled navigation landmark listing every visible section', () => {
    renderRail();
    const nav = screen.getByRole('navigation', { name: 'settings.shell.nav_label' });
    expect(
      within(nav).getByRole('button', { name: /settings\.language\.title/ })
    ).toBeInTheDocument();
    expect(
      within(nav).getByRole('button', { name: /memories\.settings\.title/ })
    ).toBeInTheDocument();
    // Tabs and groups appear as structure.
    expect(within(nav).getByText('settings.tabs.preferences')).toBeInTheDocument();
    expect(within(nav).getByText('settings.groups.personalization')).toBeInTheDocument();
  });

  it('hides the administration entries from a regular user, shows them to a superuser', () => {
    renderRail();
    expect(
      screen.queryByRole('button', { name: /settings\.admin\.users\.title/ })
    ).not.toBeInTheDocument();

    renderRail({ availability: { ...AVAILABLE, isSuperuser: true } });
    expect(
      screen.getByRole('button', { name: /settings\.admin\.users\.title/ })
    ).toBeInTheDocument();
    expect(screen.getByText('settings.tabs.administration')).toBeInTheDocument();
  });

  it('states the active section with aria-current and nothing else', () => {
    renderRail({ activeToken: 'theme' });
    const active = screen.getByRole('button', { name: /settings\.theme\.title/ });
    expect(active).toHaveAttribute('aria-current', 'true');
    const language = screen.getByRole('button', { name: /settings\.language\.title/ });
    expect(language).not.toHaveAttribute('aria-current');
  });

  it('reports a pick to the caller', async () => {
    const { user, onSelect } = renderRail();
    await user.click(screen.getByRole('button', { name: /settings\.theme\.title/ }));
    expect(onSelect).toHaveBeenCalledWith('theme');
  });
  /**
   * The rail carries the same tones — and below `lg` it IS the settings list,
   * so this is the only version of it a phone ever shows.
   */
  describe('group tones', () => {
    const glyphOf = (row: HTMLElement) => row.querySelector('svg');

    it('paints an inactive row with the tone of its group', () => {
      renderRail();
      const row = screen.getByRole('button', { name: /settings\.theme\.title/ });
      const tone = SETTINGS_GROUP_TONES[SETTINGS_SEARCH_META['theme'].group];

      expect(glyphOf(row)).toHaveClass(tone.glyph);
    });

    it('keeps the accent on the CURRENT row, so "you are here" never rests on a hue', () => {
      // Twelve tones sit in this column; if the open section were just a
      // thirteenth colour, the one piece of state here would be the hardest
      // thing to find. The row keeps the accent ink, background and weight.
      renderRail({ activeToken: 'theme' });
      const row = screen.getByRole('button', { name: /settings\.theme\.title/ });
      const tone = SETTINGS_GROUP_TONES[SETTINGS_SEARCH_META['theme'].group];

      expect(glyphOf(row)).toHaveClass('text-primary');
      expect(glyphOf(row)).not.toHaveClass(tone.glyph);
    });
  });
});
