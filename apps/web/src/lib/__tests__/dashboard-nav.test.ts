/**
 * The destination table: order, the gated meetings entry, and the one filter
 * both renderers read (a gated destination whose flag is off does not exist).
 */

import { describe, expect, it } from 'vitest';

import { DASHBOARD_DESTINATIONS, destinationPath, visibleDestinations } from '../dashboard-nav';

describe('DASHBOARD_DESTINATIONS', () => {
  it('places meetings between relations and notifications (ADR-258)', () => {
    const segments = DASHBOARD_DESTINATIONS.map(d => d.segment);
    expect(segments).toEqual([
      '',
      'chat',
      'relations',
      'meetings',
      'notifications',
      'settings',
      'faq',
    ]);
  });

  it('gates meetings on the instance flag and nothing else', () => {
    const gated = DASHBOARD_DESTINATIONS.filter(d => d.feature !== undefined);
    expect(gated.map(d => [d.segment, d.feature])).toEqual([['meetings', 'meetings_enabled']]);
  });
});

describe('visibleDestinations', () => {
  it('hides the meetings destination while the flag is off or unknown', () => {
    for (const features of [undefined, null, {}, { meetings_enabled: false }]) {
      const segments = visibleDestinations(features).map(d => d.segment);
      expect(segments).not.toContain('meetings');
      expect(segments).toHaveLength(DASHBOARD_DESTINATIONS.length - 1);
    }
  });

  it('offers it, in place, when the instance has the feature on', () => {
    const segments = visibleDestinations({ meetings_enabled: true }).map(d => d.segment);
    expect(segments).toEqual(DASHBOARD_DESTINATIONS.map(d => d.segment));
    expect(segments.indexOf('meetings')).toBe(segments.indexOf('relations') + 1);
  });

  it('routes the new destination like every other one', () => {
    expect(destinationPath('meetings')).toBe('/dashboard/meetings');
  });
});
