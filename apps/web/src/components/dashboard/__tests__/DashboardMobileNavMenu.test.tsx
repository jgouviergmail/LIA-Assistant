/**
 * The dashboard's logo menu carries the header's actions the instance offers:
 * the recorder where recording is offered, the radio where the radio is
 * (ADR-259, ADR-324) — in the header's order.
 */
import { describe, expect, it, vi } from 'vitest';

import { renderWithProviders, screen } from '@/__tests__/test-utils';
import { DASHBOARD_DESTINATIONS } from '@/lib/dashboard-nav';

vi.mock('@/lib/radio/player', () => ({
  radioPlayer: () => ({ start: vi.fn(async () => undefined), stop: vi.fn(async () => undefined) }),
}));

import { DashboardMobileNavMenu } from '../DashboardMobileNavMenu';

function renderMenu(radioEnabled: boolean) {
  return renderWithProviders(
    <DashboardMobileNavMenu
      lng="en"
      radioEnabled={radioEnabled}
      buildHref={route => `/en${route}`}
      translate={key => key}
      isActiveRoute={() => false}
      triggerLabel="Menu"
    />
  );
}

describe('DashboardMobileNavMenu', () => {
  it('offers the radio where the instance offers it', async () => {
    const { user } = renderMenu(true);
    await user.click(screen.getByRole('button', { name: 'Menu' }));
    const items = await screen.findAllByRole('menuitem');
    // No recorder provider here: the recorder is not offered, the radio is.
    expect(items).toHaveLength(DASHBOARD_DESTINATIONS.length + 1);
    expect(items.at(-1)).toHaveAccessibleName('radio.header.start');
  });

  it('offers no radio entry where the instance does not', async () => {
    const { user } = renderMenu(false);
    await user.click(screen.getByRole('button', { name: 'Menu' }));
    expect(await screen.findAllByRole('menuitem')).toHaveLength(DASHBOARD_DESTINATIONS.length);
  });
});
