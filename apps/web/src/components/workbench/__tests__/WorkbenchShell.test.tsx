/**
 * The « Tools » shell (ADR-369, ADR-227 §7): one read of the rail; on a desktop
 * the section opens the first ready tool, or names the exit when none is; below
 * `lg` the rail IS the section's screen and a tool replaces it with a way back,
 * focus moved to the tool's heading; a section switched off reads nothing.
 */

import type { ReactNode } from 'react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { renderWithProviders, screen, waitFor } from '@/__tests__/test-utils';
import type { AppConfig } from '@/hooks/useAppConfig';
import type { WorkbenchAvailability, WorkbenchToolId } from '@/lib/workbench/types';

type ShellConfig = Pick<AppConfig, 'capabilities'> & { features: { workbench_enabled?: boolean } };

const { get, replace, nav, media, config } = vi.hoisted(() => ({
  get: vi.fn(),
  replace: vi.fn(),
  nav: { pathname: '/en/dashboard/tools' },
  media: { desktop: true },
  config: { value: null as ShellConfig | null },
}));
vi.mock('@/hooks/useAuth', () => ({ useAuth: () => ({ user: { id: 'owner' } }) }));
vi.mock('@/lib/api-client', async importOriginal => ({
  ...(await importOriginal<typeof import('@/lib/api-client')>()),
  default: { get },
}));
vi.mock('@/lib/logger', () => ({
  logger: { debug: vi.fn(), error: vi.fn(), warn: vi.fn(), info: vi.fn() },
}));
vi.mock('next/navigation', () => ({
  usePathname: () => nav.pathname,
  useRouter: () => ({ replace, push: vi.fn(), back: vi.fn(), prefetch: vi.fn() }),
  useSearchParams: () => new URLSearchParams(),
}));
vi.mock('@/hooks/useMediaQuery', () => ({ useMediaQuery: () => media.desktop }));
vi.mock('@/hooks/useLocalizedRouter', () => ({
  useLocalizedRouter: () => ({ replace, push: vi.fn() }),
}));
vi.mock('@/hooks/useAppConfig', async importOriginal => ({
  ...(await importOriginal<typeof import('@/hooks/useAppConfig')>()),
  useAppConfig: () => ({ config: config.value, loading: false, error: null }),
}));

import { WorkbenchLanding } from '../WorkbenchLanding';
import { WorkbenchShell } from '../WorkbenchShell';
import { WorkbenchToolHeader } from '../WorkbenchToolHeader';

const OFFERED: ShellConfig = { features: { workbench_enabled: true }, capabilities: {} };
const ORDER: readonly WorkbenchToolId[] = [
  'mail',
  'calendar',
  'tasks',
  'contacts',
  'files',
  'lights',
];

function rail(ready: readonly WorkbenchToolId[]): WorkbenchAvailability {
  return {
    tools: ORDER.map(tool => ({
      tool,
      state: ready.includes(tool) ? 'ready' : 'not_connected',
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

function shell(children: ReactNode) {
  return renderWithProviders(<WorkbenchShell lng="en">{children}</WorkbenchShell>);
}

beforeEach(() => {
  vi.clearAllMocks();
  nav.pathname = '/en/dashboard/tools';
  media.desktop = true;
  config.value = OFFERED;
  get.mockResolvedValue(rail(['calendar', 'tasks']));
});

describe('WorkbenchShell — landing', () => {
  it('opens the first ready tool in rail order on a desktop', async () => {
    shell(<WorkbenchLanding lng="en" />);

    await waitFor(() => expect(replace).toHaveBeenCalledWith('/dashboard/tools/calendar'));
  });

  it('names the exit when no tool is ready', async () => {
    get.mockResolvedValue(rail([]));
    shell(<WorkbenchLanding lng="en" />);

    const exit = await screen.findByRole('link', { name: 'workbench.states.open_connectors' });
    expect(exit).toHaveAttribute('href', '/en/dashboard/settings?section=connectors');
    expect(replace).not.toHaveBeenCalled();
  });

  it('names the exit below lg too, under the rail, when no tool is ready', async () => {
    media.desktop = false;
    get.mockResolvedValue(rail([]));
    shell(<WorkbenchLanding lng="en" />);

    const exit = await screen.findByRole('link', { name: 'workbench.states.open_connectors' });
    expect(exit.closest('.hidden')).toBeNull();
  });

  it('opens the first ready tool below lg too: the switcher replaces the list screen', async () => {
    media.desktop = false;
    shell(<WorkbenchLanding lng="en" />);

    await waitFor(() => expect(replace).toHaveBeenCalledWith('/dashboard/tools/calendar'));
  });
});

describe('WorkbenchShell — a tool screen', () => {
  it.each([true, false])(
    'keeps the switcher above the tool and moves focus to it (desktop: %s)',
    async desktop => {
      media.desktop = desktop;
      nav.pathname = '/en/dashboard/tools/calendar';
      shell(<WorkbenchToolHeader lng="en" tool="calendar" />);

      const heading = await screen.findByRole('heading', {
        level: 1,
        name: 'workbench.tools.calendar.label',
      });
      await waitFor(() => expect(heading).toHaveFocus());
      const switcher = screen.getByRole('navigation', { name: 'workbench.rail.label' });
      expect(switcher.closest('.hidden')).toBeNull();
      expect(
        switcher.compareDocumentPosition(heading) & Node.DOCUMENT_POSITION_FOLLOWING
      ).toBeTruthy();
      // The way between tools is the switcher itself: no « all tools » detour.
      expect(screen.queryByRole('link', { name: 'workbench.rail.back' })).toBeNull();
    }
  );
});

describe('WorkbenchShell — the section switched off, or unreadable', () => {
  it('says so and reads nothing', async () => {
    config.value = {
      features: { workbench_enabled: true },
      capabilities: { workbench: { enabled: false, family: 'work' } },
    };
    shell(<WorkbenchLanding lng="en" />);

    expect(await screen.findByText('workbench.states.section_off_title')).toBeInTheDocument();
    expect(
      screen.getByRole('link', { name: 'workbench.states.back_to_dashboard' })
    ).toHaveAttribute('href', '/en/dashboard');
    expect(get).not.toHaveBeenCalled();
  });

  it('offers a retry when the rail cannot be read', async () => {
    get.mockRejectedValue(new Error('down'));
    shell(<WorkbenchLanding lng="en" />);

    expect(
      await screen.findByRole('button', { name: 'workbench.states.retry' })
    ).toBeInTheDocument();
  });

  it('keeps the error when the retry fails again, and leaves no failure unheard', async () => {
    const unheard = vi.fn();
    process.on('unhandledRejection', unheard);
    try {
      get.mockRejectedValue(new Error('down'));
      const { user } = shell(<WorkbenchLanding lng="en" />);

      await user.click(await screen.findByRole('button', { name: 'workbench.states.retry' }));
      await waitFor(() => expect(get).toHaveBeenCalledTimes(2));
      await new Promise(resolve => setTimeout(resolve, 0));

      expect(screen.getByRole('button', { name: 'workbench.states.retry' })).toBeInTheDocument();
      expect(unheard).not.toHaveBeenCalled();
    } finally {
      process.off('unhandledRejection', unheard);
    }
  });
});
