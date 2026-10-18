/**
 * The one rule for a capability's effective state (ADR-280): the operator's
 * verdict when the capability map carries it, the deployment ceiling otherwise.
 */
import { describe, expect, it } from 'vitest';

import { capabilityEnabled } from '@/lib/capability-state';

const MAP_OFF = { radio: { enabled: false, family: 'media' } };
const MAP_ON = { radio: { enabled: true, family: 'media' } };

describe('capabilityEnabled', () => {
  it('reads the operator verdict over the ceiling when the map carries the capability', () => {
    expect(capabilityEnabled(MAP_OFF, 'radio', true)).toBe(false);
    expect(capabilityEnabled(MAP_ON, 'radio', false)).toBe(true);
  });

  it('falls back to the ceiling when the map omits the capability', () => {
    expect(capabilityEnabled(MAP_ON, 'peers', true)).toBe(true);
    expect(capabilityEnabled(MAP_ON, 'peers', false)).toBe(false);
  });

  it('falls back to the ceiling when the server sends no map at all', () => {
    expect(capabilityEnabled(undefined, 'radio', true)).toBe(true);
    expect(capabilityEnabled(undefined, 'radio', undefined)).toBe(false);
  });
});
