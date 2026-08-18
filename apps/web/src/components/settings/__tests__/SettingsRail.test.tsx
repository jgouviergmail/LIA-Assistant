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
import { buildSettingsShellModel } from '@/lib/settings-shell-model';
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
});
