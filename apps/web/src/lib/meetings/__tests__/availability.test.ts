/**
 * Whether the meetings are offered now: the operator's switch when the
 * configuration carries it, the deployment ceiling otherwise.
 */
import { describe, expect, it } from 'vitest';

import { meetingsAvailable } from '@/lib/meetings/availability';

describe('meetingsAvailable', () => {
  it('follows the operator when the capability map carries the meetings', () => {
    const ceiling = { meetings_enabled: true };

    expect(
      meetingsAvailable({
        features: ceiling,
        capabilities: { meetings: { enabled: false, family: 'media' } },
      })
    ).toBe(false);
    expect(
      meetingsAvailable({
        features: {},
        capabilities: { meetings: { enabled: true, family: 'media' } },
      })
    ).toBe(true);
  });

  it('falls back to the deployment ceiling for an API that publishes no map', () => {
    expect(meetingsAvailable({ features: { meetings_enabled: true } })).toBe(true);
    expect(meetingsAvailable({ features: { meetings_enabled: true }, capabilities: {} })).toBe(
      true
    );
    expect(meetingsAvailable({ features: {} })).toBe(false);
  });

  it('offers nothing before the configuration answers', () => {
    expect(meetingsAvailable(null)).toBe(false);
    expect(meetingsAvailable(undefined)).toBe(false);
  });
});
