/**
 * The « Tools » rail (ADR-369): a named landmark of LINKS, the open tool stated
 * with `aria-current`, usable and broken tools in « Tools », the ones to
 * connect in « To connect » (pointing at Settings › Connectors), and a tool
 * the instance offers no provider for absent (D6).
 */

import { describe, expect, it } from 'vitest';

import { renderWithProviders, screen, within } from '@/__tests__/test-utils';
import { WORKBENCH_TOOLS } from '@/lib/workbench/tools';
import type {
  WorkbenchAvailability,
  WorkbenchToolId,
  WorkbenchToolState,
} from '@/lib/workbench/types';

import { WorkbenchRail } from '../WorkbenchRail';

type States = Partial<Record<WorkbenchToolId, WorkbenchToolState>>;

function availability(states: States): WorkbenchAvailability {
  return {
    tools: WORKBENCH_TOOLS.map(spec => ({
      tool: spec.id,
      state: states[spec.id] ?? 'not_connected',
      provider: null,
      features: [],
      bounds: {},
    })),
    limits: {
      page_size: 25,
      bulk_max_items: 50,
      download_max_bytes: 1,
      upload_max_bytes: 1,
      calendar_window_max_events: 500,
      send_undo_seconds: 0,
      draft_autosave_seconds: 0,
      search_max_chars: 500,
      assist_text_max_chars: 8000,
      assist_instruction_max_chars: 500,
    },
  };
}

function rail(states: States, active: WorkbenchToolId | null = null): HTMLElement {
  renderWithProviders(
    <WorkbenchRail lng="en" availability={availability(states)} activeTool={active} />
  );
  return screen.getByRole('navigation', { name: 'workbench.rail.label' });
}

describe('WorkbenchRail — whose tool it is', () => {
  it('names the vendor of the open tool, and of no other', () => {
    renderWithProviders(
      <WorkbenchRail
        lng="en"
        availability={{
          tools: [
            {
              tool: 'mail',
              state: 'ready',
              provider: 'microsoft_outlook',
              features: [],
              bounds: {},
            },
            { tool: 'tasks', state: 'ready', provider: 'google_tasks', features: [], bounds: {} },
          ],
          limits: availability({}).limits,
        }}
        activeTool="mail"
      />
    );

    expect(screen.getByRole('link', { name: /workbench.tools.mail.label/ })).toHaveTextContent(
      'Microsoft'
    );
    expect(screen.getByRole('link', { name: /workbench.tools.tasks.label/ })).not.toHaveTextContent(
      'Google'
    );
  });
});

describe('WorkbenchRail', () => {
  it('lists the usable and broken tools in « Tools », as links to their pages', () => {
    const nav = rail({ mail: 'ready', calendar: 'reconnect_required' });
    const tools = within(nav).getByRole('list', { name: 'workbench.rail.group_tools' });

    const links = within(tools).getAllByRole('link');
    expect(links.map(link => link.getAttribute('href'))).toEqual([
      '/en/dashboard/tools/mail',
      '/en/dashboard/tools/calendar',
    ]);
    const broken = links[1];
    expect(broken).toBeDefined();
    if (broken) expect(within(broken).getByText('workbench.rail.reconnect')).toBeInTheDocument();
  });

  it('sends a tool to connect to Settings › Connectors', () => {
    const nav = rail({ mail: 'ready' });
    const toConnect = within(nav).getByRole('list', { name: 'workbench.rail.group_to_connect' });

    const links = within(toConnect).getAllByRole('link');
    expect(links).toHaveLength(5);
    for (const link of links) {
      expect(link).toHaveAttribute('href', '/en/dashboard/settings?section=connectors');
    }
  });

  it('states the open tool with aria-current, and only that one', () => {
    const nav = rail({ mail: 'ready', calendar: 'ready' }, 'calendar');

    const current = within(nav)
      .getAllByRole('link')
      .filter(link => link.getAttribute('aria-current') === 'page');
    expect(current.map(link => link.getAttribute('href'))).toEqual([
      '/en/dashboard/tools/calendar',
    ]);
  });

  it('brings the open tool into view in the scrolling row, never the page', () => {
    const seen: Array<{ target: Element; options: unknown }> = [];
    const original = Element.prototype.scrollIntoView;
    Element.prototype.scrollIntoView = function (this: Element, options?: unknown) {
      seen.push({ target: this, options });
    };
    try {
      rail({ mail: 'ready', calendar: 'ready', files: 'ready' }, 'files');
    } finally {
      Element.prototype.scrollIntoView = original;
    }

    expect(seen.map(({ target }) => target.getAttribute('href'))).toEqual([
      '/en/dashboard/tools/files',
    ]);
    expect(seen[0]?.options).toEqual({ block: 'nearest', inline: 'nearest' });
  });

  it('leaves out a tool the instance offers no provider for', () => {
    const nav = rail({ mail: 'ready', lights: 'unavailable' });

    expect(within(nav).queryByText('workbench.tools.lights.label')).not.toBeInTheDocument();
  });

  it('draws no empty group', () => {
    const nav = rail({});

    expect(within(nav).queryByRole('list', { name: 'workbench.rail.group_tools' })).toBeNull();
    expect(
      within(nav).getByRole('list', { name: 'workbench.rail.group_to_connect' })
    ).toBeInTheDocument();
  });
});
