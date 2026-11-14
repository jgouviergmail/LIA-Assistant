/**
 * The destinations this instance offers NOW — the one list behind the header,
 * the menu the logo opens on a phone and the world's « Application » links.
 *
 * The deployment ceiling mounts a section's routes; the operator's switch can
 * still close them (ADR-280). A destination read from the ceiling alone stays
 * offered after the switch and leads to a refusal: the world's list did, and
 * the header's did for the meetings and the knowledge spaces.
 */
import { describe, expect, it } from 'vitest';

import { offeredDestinations, type OfferConfig } from '@/components/dashboard/offered-destinations';
import type { AppConfig } from '@/hooks/useAppConfig';
import { DASHBOARD_DESTINATIONS, type DestinationFeatures } from '@/lib/dashboard-nav';

/** Every flag a destination names, on — derived, so a new gated destination is covered. */
const CEILINGS: DestinationFeatures = Object.fromEntries(
  DASHBOARD_DESTINATIONS.flatMap(d => (d.feature ? [[d.feature, true]] : []))
);

function config(
  features: DestinationFeatures,
  capabilities?: AppConfig['capabilities']
): OfferConfig {
  return { features, ...(capabilities ? { capabilities } : {}) };
}

const segments = (value: Parameters<typeof offeredDestinations>[0]) =>
  offeredDestinations(value).map(destination => destination.segment);

describe('offeredDestinations', () => {
  it('is the whole table, in order, where the instance offers everything', () => {
    expect(segments(config(CEILINGS))).toEqual(DASHBOARD_DESTINATIONS.map(d => d.segment));
  });

  it.each([
    ['world', 'world'],
    ['workbench', 'tools'],
    ['sms', 'sms'],
    ['meetings', 'meetings'],
    ['workboard', 'workboard'],
    ['rag_spaces', 'spaces'],
  ] as const)(
    'withdraws a destination whose capability the operator switched off: %s',
    (capability, segment) => {
      const off = config(CEILINGS, { [capability]: { enabled: false, family: 'work' } });
      const on = config(CEILINGS, { [capability]: { enabled: true, family: 'work' } });

      expect(segments(off)).not.toContain(segment);
      expect(segments(on)).toContain(segment);
    }
  );

  it('reads no gated destination from a ceiling alone', () => {
    // A flag is named after its capability (`<capability>_enabled`). With every
    // ceiling on and every one of those capabilities switched off by the
    // operator, what is left is what no flag gates — a destination added to
    // the table with no door here would stay, and fail this.
    const gated = DASHBOARD_DESTINATIONS.flatMap(d => (d.feature ? [d.feature] : []));
    const everythingOff = Object.fromEntries(
      gated.map(flag => [flag.replace(/_enabled$/, ''), { enabled: false, family: 'work' }])
    );
    const ungated = DASHBOARD_DESTINATIONS.filter(d => d.feature === undefined).map(d => d.segment);

    expect(gated.length).toBeGreaterThan(0);
    expect(segments(config(CEILINGS, everythingOff))).toEqual(ungated);
  });

  it('falls back to the deployment ceiling when the map does not carry a capability', () => {
    // An older API publishes no capability map: the ceiling is all there is.
    expect(segments(config(CEILINGS, {}))).toEqual(DASHBOARD_DESTINATIONS.map(d => d.segment));
    expect(segments(config({ ...CEILINGS, sms_enabled: false }, {}))).not.toContain('sms');
    expect(segments(config({ ...CEILINGS, meetings_enabled: false }, {}))).not.toContain(
      'meetings'
    );
    expect(segments(config({ ...CEILINGS, rag_spaces_enabled: false }, {}))).not.toContain(
      'spaces'
    );
  });

  it('offers nothing gated before the configuration answers', () => {
    const ungated = DASHBOARD_DESTINATIONS.filter(d => d.feature === undefined).map(d => d.segment);

    expect(segments(null)).toEqual(ungated);
    expect(segments(undefined)).toEqual(ungated);
  });
});
