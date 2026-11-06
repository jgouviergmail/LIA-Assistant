/**
 * The rail's model (ADR-369): the six tools in their order, grouped « Tools » /
 * « To connect », the tool a desktop opens on, and the tool a URL names.
 */

import { describe, expect, it } from 'vitest';

import {
  WORKBENCH_TOOLS,
  landingTool,
  providerVendor,
  railGroups,
  toolOfPathname,
  toolPath,
} from '../tools';
import type { WorkbenchAvailability, WorkbenchToolId, WorkbenchToolState } from '../types';

function availability(
  states: Partial<Record<WorkbenchToolId, WorkbenchToolState>>
): WorkbenchAvailability {
  return {
    tools: WORKBENCH_TOOLS.map(spec => ({
      tool: spec.id,
      state: states[spec.id] ?? 'not_connected',
      provider: states[spec.id] === 'ready' ? 'provider' : null,
      features: [],
      bounds: {},
    })),
    limits: {
      page_size: 25,
      bulk_max_items: 50,
      download_max_bytes: 26_214_400,
      upload_max_bytes: 26_214_400,
      calendar_window_max_events: 500,
      send_undo_seconds: 0,
      draft_autosave_seconds: 0,
      search_max_chars: 500,
    },
  };
}

describe('providerVendor', () => {
  it('reads the vendor from the connector, and says nothing of one it does not know', () => {
    expect(providerVendor('google_gmail')).toBe('Google');
    expect(providerVendor('microsoft_outlook')).toBe('Microsoft');
    expect(providerVendor('apple_calendar')).toBe('Apple');
    expect(providerVendor('philips_hue')).toBe('Philips Hue');
    expect(providerVendor('someone_else')).toBeNull();
    expect(providerVendor(null)).toBeNull();
  });
});

describe('WORKBENCH_TOOLS', () => {
  it('lists the six tools in rail order', () => {
    expect(WORKBENCH_TOOLS.map(tool => tool.id)).toEqual([
      'mail',
      'calendar',
      'tasks',
      'contacts',
      'files',
      'lights',
    ]);
  });

  it('routes each tool under the section', () => {
    expect(toolPath('calendar')).toBe('/dashboard/tools/calendar');
  });
});

describe('railGroups', () => {
  it('keeps usable and broken tools together, the ones to connect apart, the rest out', () => {
    const groups = railGroups(
      availability({ calendar: 'ready', mail: 'reconnect_required', lights: 'unavailable' })
    );
    expect(groups.tools.map(item => [item.tool, item.state])).toEqual([
      ['mail', 'reconnect_required'],
      ['calendar', 'ready'],
    ]);
    expect(groups.toConnect.map(item => item.tool)).toEqual(['tasks', 'contacts', 'files']);
  });
});

describe('landingTool', () => {
  it('opens the first ready tool in rail order, never a broken one', () => {
    expect(landingTool(availability({ mail: 'reconnect_required', tasks: 'ready' }))).toBe('tasks');
  });

  it('opens nothing when no tool is ready', () => {
    expect(landingTool(availability({ mail: 'reconnect_required' }))).toBeNull();
    expect(landingTool(undefined)).toBeNull();
  });
});

describe('toolOfPathname', () => {
  it('reads the tool a URL names, and only a known one', () => {
    expect(toolOfPathname('/fr/dashboard/tools/calendar')).toBe('calendar');
    expect(toolOfPathname('/fr/dashboard/tools/calendar/')).toBe('calendar');
    expect(toolOfPathname('/fr/dashboard/tools')).toBeNull();
    expect(toolOfPathname('/fr/dashboard/tools/unknown')).toBeNull();
    expect(toolOfPathname('/fr/dashboard/chat')).toBeNull();
  });
});
