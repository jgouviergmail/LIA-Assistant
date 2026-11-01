/**
 * The « Tools » destination is offered by ONE verdict (ADR-369): the operator's
 * switch when the configuration carries the capability map, else the deployment
 * ceiling — and an unknown configuration offers nothing (no flash before /config).
 */

import { describe, expect, it } from 'vitest';

import { workbenchAvailable } from '../availability';

describe('workbenchAvailable', () => {
  it('offers nothing while the configuration is unknown', () => {
    expect(workbenchAvailable(undefined)).toBe(false);
    expect(workbenchAvailable(null)).toBe(false);
    expect(workbenchAvailable({})).toBe(false);
  });

  it('follows the deployment ceiling when no capability map is published', () => {
    expect(workbenchAvailable({ features: { workbench_enabled: true } })).toBe(true);
    expect(workbenchAvailable({ features: { workbench_enabled: false } })).toBe(false);
  });

  it("lets the operator's switch decide when the map carries it", () => {
    const on = { enabled: true, family: 'work' };
    const off = { enabled: false, family: 'work' };
    expect(
      workbenchAvailable({
        features: { workbench_enabled: true },
        capabilities: { workbench: off },
      })
    ).toBe(false);
    expect(
      workbenchAvailable({
        features: { workbench_enabled: false },
        capabilities: { workbench: on },
      })
    ).toBe(true);
  });
});
