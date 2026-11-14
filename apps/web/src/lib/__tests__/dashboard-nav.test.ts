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
      'world',
      'tools',
      'relations',
      'sms',
      'meetings',
      'workboard',
      'spaces',
      'notifications',
      'settings',
      'faq',
    ]);
  });

  it('gates meetings and the world on their instance availability', () => {
    const gated = DASHBOARD_DESTINATIONS.filter(d => d.feature !== undefined);
    expect(gated.map(d => [d.segment, d.feature])).toEqual([
      ['world', 'world_enabled'],
      ['tools', 'workbench_enabled'],
      ['sms', 'sms_enabled'],
      ['meetings', 'meetings_enabled'],
      ['workboard', 'workboard_enabled'],
      ['spaces', 'rag_spaces_enabled'],
    ]);
  });
});

describe('visibleDestinations', () => {
  it('hides the meetings destination while the flag is off or unknown', () => {
    for (const features of [undefined, null, {}, { meetings_enabled: false }]) {
      const segments = visibleDestinations(features).map(d => d.segment);
      expect(segments).not.toContain('meetings');
      expect(segments).not.toContain('world');
      expect(segments).not.toContain('tools');
      expect(segments).not.toContain('sms');
      expect(segments).not.toContain('spaces');
      expect(segments).not.toContain('workboard');
      expect(segments).toHaveLength(DASHBOARD_DESTINATIONS.length - 6);
    }
  });

  it('offers it, in place, when the instance has the feature on', () => {
    const segments = visibleDestinations({
      meetings_enabled: true,
      world_enabled: true,
      workbench_enabled: true,
      sms_enabled: true,
      rag_spaces_enabled: true,
      workboard_enabled: true,
    }).map(d => d.segment);
    expect(segments).toEqual(DASHBOARD_DESTINATIONS.map(d => d.segment));
    // The owner's order (2026-10-31): the tools right after the world, the
    // SMS right after the relations, then the meetings.
    expect(segments.indexOf('tools')).toBe(segments.indexOf('world') + 1);
    expect(segments.indexOf('sms')).toBe(segments.indexOf('relations') + 1);
    expect(segments.indexOf('meetings')).toBe(segments.indexOf('sms') + 1);
    // The owner (2026-11-11): the workboard right after the meetings — it had
    // no door in the header since ADR-276 (D16), only a settings section.
    expect(segments.indexOf('workboard')).toBe(segments.indexOf('meetings') + 1);
    expect(segments.indexOf('spaces')).toBe(segments.indexOf('workboard') + 1);
  });

  it('offers the workboard only where the instance offers it', () => {
    const offered = visibleDestinations({ workboard_enabled: true }).map(d => d.segment);
    expect(offered).toContain('workboard');
    expect(visibleDestinations({ workboard_enabled: false }).map(d => d.segment)).not.toContain(
      'workboard'
    );
  });

  it('routes the new destination like every other one', () => {
    expect(destinationPath('meetings')).toBe('/dashboard/meetings');
    expect(destinationPath('sms')).toBe('/dashboard/sms');
    expect(destinationPath('workboard')).toBe('/dashboard/workboard');
  });
});
