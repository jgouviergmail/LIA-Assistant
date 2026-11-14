/**
 * The world's « Application » links are the header's destinations, by the same
 * door: what the operator switched off is offered in neither.
 */
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { render, screen } from '@testing-library/react';

import { destinationPath, type DashboardDestination } from '@/lib/dashboard-nav';
import type { SettingsSearchAvailability } from '@/lib/settings-search';
import { buildLocalizedPath } from '@/utils/i18n-path-utils';
import { WorldCatalogue } from '../WorldCatalogue';

const state = vi.hoisted(() => ({
  config: null as {
    features: Record<string, boolean>;
    capabilities?: Record<string, { enabled: boolean; family: string }>;
  } | null,
}));
vi.mock('@/hooks/useAppConfig', () => ({ useAppConfig: () => ({ config: state.config }) }));

const AVAILABILITY: SettingsSearchAvailability = {
  isSuperuser: false,
  openLoopsEnabled: false,
  habitsEnabled: false,
  peersEnabled: false,
  sandboxEgressEnabled: false,
  liveEnabled: false,
  radioEnabled: false,
  channelsEnabled: false,
  psycheEnabled: false,
  journalsEnabled: false,
  skillsEnabled: false,
  mcpEnabled: false,
  ragSpacesEnabled: false,
  imageGenerationEnabled: false,
  telephonyEnabled: false,
  hapticsSupported: false,
  debugUserAccess: false,
};
const CEILINGS = { workbench_enabled: true, sms_enabled: true, workboard_enabled: true };
/** The address a destination's link carries, as the application builds it. */
const to = (segment: DashboardDestination['segment']) =>
  buildLocalizedPath(destinationPath(segment), 'fr');

function hrefs(): (string | null)[] {
  render(
    <WorldCatalogue
      lng="fr"
      availability={AVAILABILITY}
      place={null}
      onSelect={() => {}}
      onCompose={() => {}}
    />
  );
  return screen.getAllByRole('link').map(link => link.getAttribute('href'));
}

beforeEach(() => {
  state.config = null;
});

describe('WorldCatalogue — the application links', () => {
  it('offers what the header offers', () => {
    state.config = { features: CEILINGS };

    expect(hrefs()).toEqual(
      expect.arrayContaining([to('tools'), to('sms'), to('workboard'), to('relations')])
    );
  });

  it('offers nothing the operator switched off, whatever the deployment ceiling says', () => {
    const off = { enabled: false, family: 'work' };
    state.config = {
      features: CEILINGS,
      capabilities: { workbench: off, sms: off, workboard: off },
    };

    const offered = hrefs();

    for (const closed of [to('tools'), to('sms'), to('workboard')])
      expect(offered).not.toContain(closed);
    // What no switch governs is still there.
    expect(offered).toContain(to('relations'));
  });
});
