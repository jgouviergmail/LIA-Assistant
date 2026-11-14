/**
 * The door of the capabilities that have no module of their own.
 *
 * Two questions, never mixed (ADR-280): is the capability OFFERED now — the
 * operator's switch, then the deployment flag — and is its RECORD still
 * readable — the deployment flag alone, whatever the switch says.
 *
 * `/config` publishes no deployment flag for three capabilities (the psyche,
 * the personal MCP servers and image generation): the capability map alone
 * answers for them.
 *
 * One router is mounted by a flag that is not its capability's ceiling — the
 * personal MCP servers — and the map cannot say it is absent: the door reads
 * that flag too, and only an explicit « off » closes.
 */
import { describe, expect, it } from 'vitest';

import {
  CAPABILITY_CEILING,
  CAPABILITY_ROUTER_FLAGS,
  capabilityAvailable,
  capabilityMounted,
  type DoorCapability,
  type FlaggedCapability,
} from '@/lib/capability-availability';

const CAPABILITIES = Object.keys(CAPABILITY_CEILING) as DoorCapability[];
const FLAGGED = CAPABILITIES.filter(
  (capability): capability is FlaggedCapability => CAPABILITY_CEILING[capability] !== null
);
const UNFLAGGED = CAPABILITIES.filter(capability => CAPABILITY_CEILING[capability] === null);

/** The deployment flags that mount a capability, where one is published. */
function mounting(capability: DoorCapability): Record<string, boolean> {
  const flag = CAPABILITY_CEILING[capability];
  return flag === null ? {} : { [flag]: true };
}

describe('capabilityAvailable', () => {
  it.each(CAPABILITIES)('follows the operator when the map carries %s', capability => {
    expect(
      capabilityAvailable(
        {
          features: mounting(capability),
          capabilities: { [capability]: { enabled: false, family: 'x' } },
        },
        capability
      )
    ).toBe(false);
    expect(
      capabilityAvailable(
        { features: {}, capabilities: { [capability]: { enabled: true, family: 'x' } } },
        capability
      )
    ).toBe(true);
  });

  it.each(FLAGGED)('falls back to the deployment flag of %s', capability => {
    const mounted = mounting(capability);

    expect(capabilityAvailable({ features: mounted }, capability)).toBe(true);
    expect(capabilityAvailable({ features: mounted, capabilities: {} }, capability)).toBe(true);
    expect(capabilityAvailable({ features: {} }, capability)).toBe(false);
  });

  it.each(CAPABILITIES)('offers no %s before the configuration answers', capability => {
    expect(capabilityAvailable(null, capability)).toBe(false);
    expect(capabilityAvailable(undefined, capability)).toBe(false);
  });

  it('takes the value a caller names for a deployment that publishes no flag', () => {
    // The attachments predate their flag: an API that says nothing has them.
    expect(capabilityAvailable({ features: {} }, 'attachments', true)).toBe(true);
    expect(
      capabilityAvailable({ features: { attachments_enabled: false } }, 'attachments', true)
    ).toBe(false);
    expect(
      capabilityAvailable(
        { features: {}, capabilities: { attachments: { enabled: false, family: 'media' } } },
        'attachments',
        true
      )
    ).toBe(false);
  });
});

describe('a capability whose deployment flag is not published', () => {
  it('is three capabilities, and nothing else', () => {
    expect([...UNFLAGGED].sort()).toEqual(['image_generation', 'mcp', 'psyche']);
  });

  it.each(UNFLAGGED)('%s is answered by the capability map alone', capability => {
    // The map carries the deployment ceiling AND the switch: a deployment that
    // does not mount the capability says « off » there too.
    expect(
      capabilityAvailable(
        { features: {}, capabilities: { [capability]: { enabled: false, family: 'x' } } },
        capability
      )
    ).toBe(false);
    expect(
      capabilityAvailable(
        { features: {}, capabilities: { [capability]: { enabled: true, family: 'x' } } },
        capability
      )
    ).toBe(true);
  });

  it.each(UNFLAGGED)('%s is offered by a server that publishes no map', capability => {
    // Such a server predates the switches: its sections were always there.
    expect(capabilityAvailable({ features: {} }, capability)).toBe(true);
    expect(capabilityAvailable({ features: {}, capabilities: {} }, capability)).toBe(true);
  });
});

describe("a router its capability's ceiling does not mount", () => {
  const offered = { mcp: { enabled: true, family: 'reach' } };

  it('is the personal MCP servers, and nothing else', () => {
    expect(CAPABILITY_ROUTER_FLAGS).toEqual({ mcp: ['mcp_user_enabled'] });
  });

  it('closes what the map offers once the deployment mounts no router', () => {
    // The instance's own MCP servers on, the personal ones off: the map says
    // « offered » and every route of the section answers 404.
    const unmounted = { mcp_user_enabled: false };

    expect(capabilityAvailable({ features: unmounted, capabilities: offered }, 'mcp')).toBe(false);
    expect(capabilityAvailable({ features: unmounted }, 'mcp')).toBe(false);
  });

  it('leaves the map its verdict where the router is mounted', () => {
    const mounted = { mcp_user_enabled: true };

    expect(capabilityAvailable({ features: mounted, capabilities: offered }, 'mcp')).toBe(true);
    expect(
      capabilityAvailable(
        { features: mounted, capabilities: { mcp: { enabled: false, family: 'reach' } } },
        'mcp'
      )
    ).toBe(false);
  });

  it('closes nothing for a server that does not publish the flag', () => {
    // An API older than the flag: the capability was offered, and still is.
    expect(capabilityAvailable({ features: {}, capabilities: offered }, 'mcp')).toBe(true);
  });

  it('touches no other capability', () => {
    expect(
      capabilityAvailable(
        {
          features: { mcp_user_enabled: false },
          capabilities: { psyche: { enabled: true, family: 'knowledge' } },
        },
        'psyche'
      )
    ).toBe(true);
  });
});

describe('capabilityMounted', () => {
  it('keeps a stored telephony key reachable under the switch, never without the flag', () => {
    // The key is the person's record; the wizard and the calls are the capability.
    const switchedOff = {
      features: { telephony_enabled: true },
      capabilities: { telephony: { enabled: false, family: 'media' } },
    };

    expect(capabilityMounted(switchedOff, 'telephony')).toBe(true);
    expect(capabilityAvailable(switchedOff, 'telephony')).toBe(false);
    expect(capabilityMounted({ features: { telephony_enabled: false } }, 'telephony')).toBe(false);
    expect(capabilityMounted({ features: {} }, 'telephony')).toBe(false);
  });

  it('reads the deployment flag alone: a record outlives the switch', () => {
    const switchedOff = {
      features: { habits_enabled: true },
      capabilities: { habits: { enabled: false, family: 'knowledge' } },
    };

    expect(capabilityMounted(switchedOff, 'habits')).toBe(true);
    expect(capabilityAvailable(switchedOff, 'habits')).toBe(false);
    expect(capabilityMounted({ features: {} }, 'habits')).toBe(false);
    expect(capabilityMounted(null, 'habits')).toBe(false);
    expect(capabilityMounted({ features: {} }, 'attachments', true)).toBe(true);
  });
});
