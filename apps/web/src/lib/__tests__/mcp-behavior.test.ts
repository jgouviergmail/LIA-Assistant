import { describe, expect, it } from 'vitest';

import {
  confirmationChoiceOf,
  confirmationValueOf,
  driverAvailability,
  driverOf,
  driverValues,
  isMcpApp,
  MCP_CONFIRMATION_CHOICES,
  MCP_DRIVERS,
  type UserMCPDefaults,
} from '../mcp-behavior';
import { mcpBehaviorFixture } from '@/__tests__/fixtures/mcp-behavior';

const DEFAULTS: UserMCPDefaults = {
  confirmation_instance: false,
  confirmation_account: null,
  confirmation_effective: false,
  react_direct_tools_default: true,
  dedicated_agents_available: true,
};

describe('confirmation choice (spec 2026-10-30 D3)', () => {
  it('reads the three stored states and writes them back', () => {
    for (const choice of MCP_CONFIRMATION_CHOICES) {
      expect(confirmationChoiceOf(confirmationValueOf(choice))).toBe(choice);
    }
    expect(confirmationValueOf('always')).toBe(true);
    expect(confirmationValueOf('as_declared')).toBe(false);
    expect(confirmationValueOf('inherit')).toBeNull();
  });

  it('reads a missing value as « like the level below »', () => {
    expect(confirmationChoiceOf(undefined)).toBe('inherit');
  });
});

describe('who drives a server (spec 2026-10-30 D4)', () => {
  it('reads the two stored values as one choice', () => {
    expect(driverOf(false, null, DEFAULTS)).toBe('direct');
    expect(driverOf(true, true, DEFAULTS)).toBe('pipeline_agent');
    expect(driverOf(true, false, DEFAULTS)).toBe('agent_everywhere');
  });

  it('an untouched shape follows the instance default', () => {
    expect(driverOf(true, null, DEFAULTS)).toBe('pipeline_agent');
    expect(driverOf(true, null, { ...DEFAULTS, react_direct_tools_default: false })).toBe(
      'agent_everywhere'
    );
  });

  it('without dedicated agents on the instance, every server is driven directly', () => {
    expect(driverOf(true, false, { ...DEFAULTS, dedicated_agents_available: false })).toBe(
      'direct'
    );
  });

  it('writes the two stored values back', () => {
    expect(driverValues('direct')).toEqual({ iterative_mode: false });
    expect(driverValues('pipeline_agent')).toEqual({
      iterative_mode: true,
      react_expand_iterative: true,
    });
    expect(driverValues('agent_everywhere')).toEqual({
      iterative_mode: true,
      react_expand_iterative: false,
    });
  });

  it('offers only what applies, saying why the rest is not', () => {
    expect(MCP_DRIVERS.map(d => driverAvailability(d, DEFAULTS, false))).toEqual([
      'available',
      'available',
      'available',
    ]);
    // An MCP App keeps its dedicated agent in ReAct: « tools directly in ReAct » is not offered.
    expect(driverAvailability('pipeline_agent', DEFAULTS, true)).toBe('mcp_app');
    const off = { ...DEFAULTS, dedicated_agents_available: false };
    expect(driverAvailability('pipeline_agent', off, false)).toBe('dedicated_agents_off');
    expect(driverAvailability('agent_everywhere', off, false)).toBe('dedicated_agents_off');
    expect(driverAvailability('direct', off, true)).toBe('available');
  });
});

describe('an MCP App (spec 2026-10-30 D4)', () => {
  it('is known from the synthesis, and unknown until it is read', () => {
    expect(isMcpApp(mcpBehaviorFixture({ notes: ['tools_unknown', 'mcp_app'] }))).toBe(true);
    expect(isMcpApp(mcpBehaviorFixture({ notes: ['tools_unknown'] }))).toBe(false);
    expect(isMcpApp(undefined)).toBe(false);
  });
});
