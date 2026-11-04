/**
 * The « Tools » calendar screen (ADR-369, Task 5.2).
 *
 * The week holding the day the address names, drawn from the calendars this
 * device shows; the open event beside it, its guests' answers told by an icon
 * and a word (colour never alone); what could not be read said above the
 * view; a new event leaves as wall times and the account's zone; « tell the
 * guests » offered only where the provider lets the page choose.
 */

import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { fireEvent, renderWithProviders, screen, waitFor, within } from '@/__tests__/test-utils';
import type { AppConfig } from '@/hooks/useAppConfig';
import type {
  CalendarEvent,
  CalendarEventDetail,
  CalendarEventsWindow,
  WorkbenchAvailability,
  WorkbenchCalendar,
  WorkbenchFeature,
} from '@/lib/workbench/types';

type ShellConfig = Pick<AppConfig, 'capabilities'> & { features: { workbench_enabled?: boolean } };

const { api, nav, toast, media } = vi.hoisted(() => ({
  api: { get: vi.fn(), post: vi.fn(), patch: vi.fn(), put: vi.fn(), delete: vi.fn() },
  nav: { search: '', push: vi.fn(), replace: vi.fn() },
  toast: { error: vi.fn(), success: vi.fn() },
  /** Whether the event opens beside the view (from xl) or in its place. */
  media: { wide: true },
}));
vi.mock('@/hooks/useAuth', () => ({
  useAuth: () => ({ user: { id: 'owner', timezone: 'Europe/Paris' } }),
}));
vi.mock('@/lib/api-client', async importOriginal => ({
  ...(await importOriginal<typeof import('@/lib/api-client')>()),
  default: api,
}));
vi.mock('@/lib/logger', () => ({
  logger: { debug: vi.fn(), error: vi.fn(), warn: vi.fn(), info: vi.fn() },
}));
vi.mock('sonner', () => ({ toast }));
vi.mock('next/navigation', () => ({
  usePathname: () => '/en/dashboard/tools/calendar',
  useRouter: () => ({ push: nav.push, replace: nav.replace, back: vi.fn(), prefetch: vi.fn() }),
  useSearchParams: () => new URLSearchParams(nav.search),
}));
vi.mock('@/hooks/useMediaQuery', () => ({
  useMediaQuery: (query: string) => (query === '(min-width: 1280px)' ? media.wide : true),
}));
vi.mock('@/hooks/useAppConfig', async importOriginal => ({
  ...(await importOriginal<typeof import('@/hooks/useAppConfig')>()),
  useAppConfig: () => ({
    config: { features: { workbench_enabled: true }, capabilities: {} } satisfies ShellConfig,
    loading: false,
    error: null,
  }),
}));

import { WorkbenchShell } from '../../WorkbenchShell';
import { CalendarTool } from '../CalendarTool';

const GOOGLE: WorkbenchFeature[] = ['all_day', 'conference', 'notify_attendees', 'occurrence_edit'];
const GRAPH: WorkbenchFeature[] = ['all_day', 'conference', 'occurrence_edit'];

function rail(features: WorkbenchFeature[]): WorkbenchAvailability {
  return {
    tools: [
      {
        tool: 'calendar',
        state: 'ready',
        provider: 'google_calendar',
        features,
        bounds: {
          window_max_days: 42,
          calendars_max: 25,
          summary_max_chars: 1024,
          location_max_chars: 1024,
          description_max_chars: 8192,
          attendees_max: 100,
        },
      },
    ],
    limits: {
      page_size: 25,
      bulk_max_items: 50,
      download_max_bytes: 26214400,
      calendar_window_max_events: 500,
    },
  };
}

const CALENDARS: WorkbenchCalendar[] = [
  { id: 'primary', name: 'Work', color: '#7c3aed', primary: true, writable: true },
  { id: 'family', name: 'Family', color: '#16a34a', primary: false, writable: true },
];

function event(id: string, overrides: Partial<CalendarEvent> = {}): CalendarEvent {
  return {
    id,
    calendar_id: 'primary',
    summary: `Event ${id}`,
    all_day: false,
    start: '2026-11-02T09:00:00Z',
    end: '2026-11-02T10:00:00Z',
    location: null,
    recurring: false,
    conference_url: null,
    ...overrides,
  };
}

const DETAIL: CalendarEventDetail = {
  ...event('e1', { summary: 'Budget review', location: 'Atlas room' }),
  description: 'Numbers first.',
  attendees: [
    { email: 'ana@example.org', name: 'Ana', response: 'accepted' },
    { email: 'theo@example.org', name: 'Théo', response: 'declined' },
  ],
  organizer: 'ana@example.org',
  link: null,
};

let features: WorkbenchFeature[];
let windowAnswer: CalendarEventsWindow;

beforeEach(() => {
  vi.clearAllMocks();
  window.localStorage.clear();
  media.wide = true;
  nav.search = 'day=2026-11-04&view=week';
  features = GOOGLE;
  windowAnswer = {
    calendars: [
      {
        calendar_id: 'primary',
        events: [
          event('e1', { summary: 'Budget review' }),
          event('off', {
            summary: 'Day off',
            all_day: true,
            start: '2026-11-03',
            end: '2026-11-05',
          }),
        ],
        truncated: false,
        skipped: 0,
        error: null,
      },
      {
        calendar_id: 'family',
        events: [event('f1', { calendar_id: 'family', summary: 'Piano' })],
        truncated: false,
        skipped: 0,
        error: null,
      },
    ],
  };
  api.get.mockImplementation((path: string) => {
    if (path === '/workbench') return Promise.resolve(rail(features));
    if (path === '/workbench/calendar/calendars') return Promise.resolve({ calendars: CALENDARS });
    if (path === '/workbench/calendar/events') return Promise.resolve(windowAnswer);
    if (path === '/workbench/calendar/event') return Promise.resolve(DETAIL);
    return Promise.resolve({});
  });
  api.post.mockResolvedValue(DETAIL);
  api.patch.mockResolvedValue(DETAIL);
});

function tool() {
  return (
    <WorkbenchShell lng="en">
      <CalendarTool lng="en" />
    </WorkbenchShell>
  );
}

function screenOf() {
  return renderWithProviders(tool());
}

function windowCalls(): Array<Record<string, unknown>> {
  return api.get.mock.calls
    .filter(([path]) => path === '/workbench/calendar/events')
    .map(([, options]) => (options as { params: Record<string, unknown> }).params);
}

describe('CalendarTool — the week', () => {
  it('reads the week holding the day, from the locale’s first weekday, every calendar shown', async () => {
    screenOf();

    expect(await screen.findByRole('link', { name: /Budget review/ })).toBeInTheDocument();
    // English reads as en-US here: its weeks start on Sunday.
    expect(windowCalls().at(-1)).toEqual({
      calendar_ids: ['primary', 'family'],
      start: '2026-11-01',
      end: '2026-11-07',
    });
    expect(screen.getByText('workbench.calendar.zone_note')).toBeInTheDocument();
  });

  it('draws an all-day event in the all-day row, in its calendar’s colour', async () => {
    screenOf();

    const bar = await screen.findByRole('link', { name: /Day off/ });
    expect(bar.getAttribute('style')).toContain('border-left-color: rgb(124, 58, 237)');
    expect(bar.getAttribute('href')).toBe(
      '/en/dashboard/tools/calendar?view=week&day=2026-11-04&cal=primary&event=off'
    );
  });

  it('counts what passes the column budget, a link to that day in the agenda', async () => {
    windowAnswer = {
      calendars: [
        {
          calendar_id: 'primary',
          events: Array.from({ length: 5 }, (_, index) => event(`x${index}`)),
          truncated: false,
          skipped: 0,
          error: null,
        },
      ],
    };
    screenOf();

    const more = await screen.findByRole('link', { name: 'workbench.calendar.more_label' });
    expect(more.getAttribute('href')).toBe(
      '/en/dashboard/tools/calendar?view=agenda&day=2026-11-02'
    );
    expect(screen.getAllByRole('link', { name: /Event x/ })).toHaveLength(2);
  });

  it('reads no calendar this device hides, and remembers it', async () => {
    const { user } = screenOf();
    await screen.findByRole('link', { name: /Budget review/ });

    await user.click(screen.getByRole('checkbox', { name: /Family/ }));

    await waitFor(() => expect(windowCalls().at(-1)?.calendar_ids).toEqual(['primary']));
    expect(window.localStorage.getItem('lia_workbench_calendar_hidden:owner')).toBe('["family"]');
  });

  it('says a calendar it could not read, and a calendar cut at the bound', async () => {
    windowAnswer = {
      calendars: [
        { calendar_id: 'primary', events: [], truncated: true, skipped: 0, error: null },
        {
          calendar_id: 'family',
          events: [],
          truncated: false,
          skipped: 2,
          error: 'provider_refused',
        },
      ],
    };
    screenOf();

    expect(await screen.findByText('workbench.calendar.calendar_failed')).toBeInTheDocument();
    expect(screen.getByText('workbench.calendar.truncated')).toBeInTheDocument();
    expect(screen.getByText('workbench.calendar.skipped')).toBeInTheDocument();
  });
});

describe('CalendarTool — the month', () => {
  it('draws six weeks and steps a month at a time', async () => {
    nav.search = 'day=2026-11-04&view=month';
    const { user } = screenOf();

    expect(
      await screen.findByRole('grid', { name: 'workbench.calendar.views.month' })
    ).toBeInTheDocument();
    expect(windowCalls().at(-1)).toMatchObject({ start: '2026-11-01', end: '2026-12-12' });

    await user.click(screen.getByRole('button', { name: 'workbench.calendar.next_month' }));
    expect(nav.replace).toHaveBeenLastCalledWith(
      '/en/dashboard/tools/calendar?view=month&day=2026-12-01',
      { scroll: false }
    );
  });

  it('moves the view to the day picked in the small month', async () => {
    const { user } = screenOf();
    await screen.findByRole('link', { name: /Budget review/ });

    await user.click(screen.getByRole('button', { name: 'Thursday, November 12' }));

    expect(nav.replace).toHaveBeenLastCalledWith(
      '/en/dashboard/tools/calendar?view=week&day=2026-11-12',
      { scroll: false }
    );
  });
});

describe('CalendarTool — the open event', () => {
  beforeEach(() => {
    nav.search = 'day=2026-11-04&view=week&cal=primary&event=e1';
  });

  it('shows who answered what by an icon and a word, never by colour alone', async () => {
    screenOf();

    const detail = await screen.findByRole('article', { name: 'Budget review' });
    expect(within(detail).getByText('workbench.calendar.organizer')).toBeInTheDocument();
    expect(within(detail).getByText('workbench.calendar.responses.declined')).toBeInTheDocument();
    expect(within(detail).getByText('Atlas room')).toBeInTheDocument();
    expect(api.get).toHaveBeenCalledWith('/workbench/calendar/event', {
      params: { calendar_id: 'primary', event_id: 'e1' },
      signal: expect.any(AbortSignal),
    });
  });

  it('offers « tell the guests » on a change only where the provider lets the page choose', async () => {
    const { user } = screenOf();
    await user.click(await screen.findByRole('button', { name: 'workbench.calendar.edit' }));
    expect(
      screen.getByRole('checkbox', { name: 'workbench.calendar.editor.notify' })
    ).toBeChecked();
  });

  it('offers no choice where the provider tells the guests its own way', async () => {
    features = GRAPH;
    const { user } = screenOf();
    await user.click(await screen.findByRole('button', { name: 'workbench.calendar.edit' }));
    expect(
      screen.queryByRole('checkbox', { name: 'workbench.calendar.editor.notify' })
    ).not.toBeInTheDocument();
  });
});

describe('CalendarTool — the focus, where the event takes the view’s place', () => {
  it('goes to the event when it opens and back to its link when it closes', async () => {
    media.wide = false;
    const { rerender } = screenOf();
    const link = await screen.findByRole('link', { name: /Budget review/ });

    nav.search = 'day=2026-11-04&view=week&cal=primary&event=e1';
    rerender(tool());
    const close = await screen.findByRole('button', { name: 'workbench.calendar.close_event' });
    await waitFor(() => expect(close).toHaveFocus());

    nav.search = 'day=2026-11-04&view=week';
    rerender(tool());
    await waitFor(() => expect(screen.getByRole('link', { name: /Budget review/ })).toHaveFocus());
    expect(link).toBeInTheDocument();
  });
});

describe('CalendarTool — a new event', () => {
  afterEach(() => vi.useRealTimers());

  it('leaves as wall times and the account’s zone, with one key per form', async () => {
    // Another day than today, whatever the real date: today a new event starts at
    // the next hour, so on the real clock this failed on the very day it names.
    vi.setSystemTime(new Date('2026-11-03T12:00:00Z'));
    nav.search = 'day=2026-11-04&view=week';
    const { user } = screenOf();
    await screen.findByRole('link', { name: /Budget review/ });

    await user.click(screen.getAllByRole('button', { name: 'workbench.calendar.new_event' })[0]);
    await user.type(screen.getByLabelText('workbench.calendar.editor.summary'), 'Dentist');
    await user.click(screen.getByRole('button', { name: 'workbench.calendar.editor.create' }));

    await waitFor(() => expect(api.post).toHaveBeenCalled());
    const [path, body] = api.post.mock.calls[0];
    expect(path).toBe('/workbench/calendar/events');
    expect(body).toMatchObject({
      calendar_id: 'primary',
      summary: 'Dentist',
      start: '2026-11-04T09:00',
      end: '2026-11-04T10:00',
      all_day: false,
      timezone: 'Europe/Paris',
    });
    expect(body.idempotency_key).toMatch(/^[0-9a-f-]{36}$/);
  });
});

describe('CalendarTool — panes sized by hand', () => {
  it('names its separator and drives the pane it sits beside, back to the layout on Enter', async () => {
    screenOf();
    const separator = await screen.findByRole('separator', {
      name: 'workbench.panes.calendar_calendars',
    });
    const pane = document.getElementById(separator.getAttribute('aria-controls') ?? '');

    expect(pane?.tagName).toBe('ASIDE');
    fireEvent.keyDown(separator, { key: 'End' });
    expect(pane?.style.getPropertyValue('--pane-w')).toMatch(/^\d+px$/);
    fireEvent.keyDown(separator, { key: 'Enter' });
    expect(pane?.style.getPropertyValue('--pane-w')).toBe('');
  });
});
