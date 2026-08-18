/**
 * SettingsOverview — the desktop landing pane of the master-detail shell.
 *
 * Cards, not rows: each visible section as a clickable card carrying its icon,
 * title and description (the same i18n keys the section header renders), under
 * real `SettingsGroupLabel` h2 headings — the overview owns the page outline,
 * the rail deliberately does not. Clicking a card opens the section, exactly
 * like the rail.
 */

import { describe, expect, it, vi } from 'vitest';

import { renderWithProviders, screen } from '@/__tests__/test-utils';
import { buildSettingsShellModel } from '@/lib/settings-shell-model';
import type { SettingsSearchAvailability } from '@/lib/settings-search';

import { SettingsOverview } from '../SettingsOverview';

const AVAILABLE: SettingsSearchAvailability = {
  isSuperuser: false,
  openLoopsEnabled: true,
  habitsEnabled: true,
  peersEnabled: true,
  debugUserAccess: true,
};

function renderOverview({
  availability = AVAILABLE,
  children = undefined as React.ReactNode,
} = {}) {
  const onSelect = vi.fn();
  const model = buildSettingsShellModel(availability);
  const view = renderWithProviders(
    <SettingsOverview lng="en" model={model} onSelect={onSelect}>
      {children}
    </SettingsOverview>
  );
  return { ...view, onSelect };
}

describe('SettingsOverview', () => {
  it('renders every visible section as a card with its title and description', () => {
    renderOverview();
    const themeCard = screen.getByRole('button', { name: /settings\.theme\.title/ });
    expect(themeCard).toBeInTheDocument();
    expect(themeCard).toHaveTextContent('settings.theme.description');
  });

  it('structures the page with real group headings', () => {
    renderOverview();
    expect(
      screen.getByRole('heading', { level: 2, name: /settings\.groups\.personalization/ })
    ).toBeInTheDocument();
  });

  it('shows administration cards to a superuser only', () => {
    renderOverview();
    expect(
      screen.queryByRole('button', { name: /settings\.admin\.users\.title/ })
    ).not.toBeInTheDocument();

    renderOverview({ availability: { ...AVAILABLE, isSuperuser: true } });
    expect(
      screen.getByRole('button', { name: /settings\.admin\.users\.title/ })
    ).toBeInTheDocument();
  });

  it('opens the picked section', async () => {
    const { user, onSelect } = renderOverview();
    await user.click(screen.getByRole('button', { name: /settings\.theme\.title/ }));
    expect(onSelect).toHaveBeenCalledWith('theme');
  });

  it('hosts a top slot — the portrait shortcut lives here', () => {
    renderOverview({ children: <p>portrait slot</p> });
    expect(screen.getByText('portrait slot')).toBeInTheDocument();
  });
});
