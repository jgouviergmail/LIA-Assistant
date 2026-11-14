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

import {
  answerConfirmDialog,
  fireEvent,
  renderWithProviders,
  screen,
  waitFor,
  within,
} from '@/__tests__/test-utils';
import type { AppConfig } from '@/hooks/useAppConfig';
import { ApiError } from '@/lib/api-client';
import type {
  CalendarEvent,
  CalendarEventDetail,
  CalendarEventsWindow,
  DueTasks,
  WorkbenchAvailability,
  WorkbenchCalendar,
  WorkbenchFeature,
} from '@/lib/workbench/types';

type ShellConfig = Pick<AppConfig, 'capabilities'> & { features: { workbench_enabled?: boolean } };

const { api, nav, toast, media } = vi.hoisted(() => ({
  api: { get: vi.fn(), post: vi.fn(), patch: vi.fn(), put: vi.fn(), delete: vi.fn() },
  nav: { search: '', push: vi.fn(), replace: vi.fn() },
  toast: { error: vi.fn(), success: vi.fn() },
  /** Whether the event opens beside the view (from xl) or in its place, and a phone's width. */
  media: { wide: true, phone: false },
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
  useMediaQuery: (query: string) => {
    if (query === '(min-width: 1280px)') return media.wide;
    return query === '(min-width: 640px)' ? !media.phone : true;
  },
}));
vi.mock('@/hooks/useAppConfig', async importOriginal => ({
  ...(await importOriginal<typeof import('@/hooks/useAppConfig')>()),
  useAppConfig: () => ({
    config: { features: { workbench_enabled: true }, capabilities: {} } satisfies ShellConfig,
    loading: false,
    error: null,
  }),
}));

import { handOff, setHandoffOwner } from '@/lib/workbench/handoff';

import { WorkbenchShell } from '../../WorkbenchShell';
import { CalendarTool } from '../CalendarTool';

const GOOGLE: WorkbenchFeature[] = [
  'all_day',
  'conference',
  'notify_attendees',
  'occurrence_edit',
  'event_move',
  'event_move_with_guests',
  'calendar_management',
];
const GRAPH: WorkbenchFeature[] = [
  'all_day',
  'conference',
  'occurrence_edit',
  'event_move',
  'calendar_management',
];

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
      upload_max_bytes: 26214400,
      calendar_window_max_events: 500,
      send_undo_seconds: 0,
      draft_autosave_seconds: 0,
      search_max_chars: 500,
      assist_text_max_chars: 8000,
      assist_instruction_max_chars: 500,
    },
  };
}

const CALENDARS: WorkbenchCalendar[] = [
  {
    id: 'primary',
    name: 'Work',
    color: '#7c3aed',
    primary: true,
    default: false,
    writable: true,
    manageable: false,
  },
  {
    id: 'family',
    name: 'Family',
    color: '#16a34a',
    primary: false,
    default: false,
    writable: true,
    manageable: true,
  },
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
  ...event('e1', { summary: 'Budget review', location: 'https://meet.example.org/atlas' }),
  description: 'Numbers first, on https://docs.example.org/budget.',
  attendees: [
    { email: 'ana@example.org', name: 'Ana', response: 'accepted' },
    { email: 'theo@example.org', name: 'Théo', response: 'declined' },
  ],
  organizer: 'ana@example.org',
  link: null,
  reminder_minutes: null,
  busy: true,
  private: false,
  zone: null,
  my_response: null,
};

let features: WorkbenchFeature[];
let windowAnswer: CalendarEventsWindow;

beforeEach(() => {
  vi.clearAllMocks();
  window.localStorage.clear();
  media.wide = true;
  media.phone = false;
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
  it('opens a card calendar despite its hidden preference, without changing that preference', async () => {
    nav.search += '&cal=family';
    window.localStorage.setItem('lia_workbench_calendar_hidden:owner', '["family"]');
    screenOf();

    const target = await screen.findByRole('status', { name: 'Family' });
    await waitFor(() => expect(target).toHaveFocus());
    expect(windowCalls().at(-1)?.calendar_ids).toContain('family');
    expect(screen.getByRole('checkbox', { name: 'Family' })).toBeChecked();
    expect(window.localStorage.getItem('lia_workbench_calendar_hidden:owner')).toBe('["family"]');
    expect(api.post).not.toHaveBeenCalled();
    expect(api.patch).not.toHaveBeenCalled();
  });

  it('says when the calendar named by a card is no longer present', async () => {
    nav.search += '&cal=missing';
    screenOf();

    expect(await screen.findByText('workbench.states.calendar_target_missing')).toBeInTheDocument();
    expect(api.get.mock.calls.some(([path]) => path === '/workbench/calendar/event')).toBe(false);
    expect(api.post).not.toHaveBeenCalled();
  });

  it('lets the reader hide a temporarily revealed calendar without changing its stored choice', async () => {
    nav.search += '&cal=family';
    window.localStorage.setItem('lia_workbench_calendar_hidden:owner', '["family"]');
    const { user } = screenOf();
    await screen.findByRole('status', { name: 'Family' });

    await user.click(screen.getByRole('checkbox', { name: 'Family' }));
    expect(nav.replace).toHaveBeenCalledWith(
      '/en/dashboard/tools/calendar?view=week&day=2026-11-04',
      { scroll: false }
    );
    expect(window.localStorage.getItem('lia_workbench_calendar_hidden:owner')).toBe('["family"]');
    expect(api.patch).not.toHaveBeenCalled();
  });

  it('does not confuse a failed calendar lookup with a missing target', async () => {
    nav.search += '&cal=family';
    const get = api.get.getMockImplementation();
    api.get.mockImplementation((path: string, options?: unknown) =>
      path === '/workbench/calendar/calendars'
        ? Promise.reject(new Error('network'))
        : get?.(path, options)
    );
    screenOf();

    expect(await screen.findByText('workbench.calendar.failed')).toBeInTheDocument();
    expect(screen.queryByText('workbench.states.calendar_target_missing')).toBeNull();
    expect(api.post).not.toHaveBeenCalled();
  });

  it('resolves the own-calendar alias to the actual loaded id on a phone', async () => {
    nav.search += '&cal=primary';
    media.phone = true;
    const get = api.get.getMockImplementation();
    api.get.mockImplementation((path: string, options?: unknown) =>
      path === '/workbench/calendar/calendars'
        ? Promise.resolve({ calendars: [{ ...CALENDARS[0], id: 'owner@example.test' }] })
        : get?.(path, options)
    );
    screenOf();

    const target = await screen.findByRole('status', { name: 'Work' });
    await waitFor(() => expect(target).toHaveFocus());
    expect(windowCalls().at(-1)?.calendar_ids).toEqual(['owner@example.test']);
    expect(api.post).not.toHaveBeenCalled();
  });

  it('reads the week holding the day, from the locale’s first weekday, every calendar shown', async () => {
    screenOf();

    expect(await screen.findByRole('link', { name: /Budget review/ })).toBeInTheDocument();
    // English reads as en-US here: its weeks start on Sunday.
    expect(windowCalls().at(-1)).toEqual({
      calendar_ids: ['primary', 'family'],
      start: '2026-11-01',
      end: '2026-11-07',
    });
    expect(screen.queryByText('workbench.calendar.zone_note')).toBeNull();
  });

  it('re-reads what it shows when the person asks', async () => {
    const { user } = screenOf();
    await screen.findByRole('button', { name: 'workbench.states.refresh' });
    await screen.findByRole('grid');
    api.get.mockClear();

    await user.click(screen.getByRole('button', { name: 'workbench.states.refresh' }));

    await waitFor(() =>
      expect(api.get).toHaveBeenCalledWith('/workbench/calendar/calendars', expect.anything())
    );
    await waitFor(() =>
      expect(api.get).toHaveBeenCalledWith('/workbench/calendar/events', expect.anything())
    );
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

describe('CalendarTool — where a new event goes', () => {
  async function chosenCalendar(calendars: WorkbenchCalendar[]): Promise<string> {
    const read = api.get.getMockImplementation();
    api.get.mockImplementation((path: string, options?: unknown) =>
      path === '/workbench/calendar/calendars'
        ? Promise.resolve({ calendars })
        : read?.(path, options)
    );
    const { user } = screenOf();

    const [newEvent] = await screen.findAllByRole('button', {
      name: 'workbench.calendar.new_event',
    });
    await user.click(newEvent!);

    const field = await screen.findByRole('combobox', {
      name: 'workbench.calendar.editor.calendar',
    });
    return (field as HTMLSelectElement).value;
  }

  it('is the calendar the settings chose', async () => {
    const chosen = [CALENDARS[0]!, { ...CALENDARS[1]!, default: true }];

    expect(await chosenCalendar(chosen)).toBe('family');
  });

  it('is the account’s own when the one chosen cannot be written', async () => {
    const chosen = [
      { ...CALENDARS[1]!, id: 'team' },
      CALENDARS[0]!,
      { ...CALENDARS[1]!, default: true, writable: false },
    ];

    expect(await chosenCalendar(chosen)).toBe('primary');
  });

  it('is the account’s own when none was chosen', async () => {
    expect(await chosenCalendar(CALENDARS)).toBe('primary');
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

  it('names the account’s own calendar by its real id when the home named it by its alias', async () => {
    // The home's agenda reads the calendar the settings chose, else `primary` (2026-11-07): an
    // alias the provider understands, the calendars list does not.
    const own = { ...CALENDARS[0], id: 'me@example.org' };
    api.get.mockImplementation((path: string) => {
      if (path === '/workbench') return Promise.resolve(rail(features));
      if (path === '/workbench/calendar/calendars')
        return Promise.resolve({ calendars: [own, CALENDARS[1]] });
      if (path === '/workbench/calendar/events') return Promise.resolve(windowAnswer);
      if (path === '/workbench/calendar/event') return Promise.resolve(DETAIL);
      return Promise.resolve({});
    });
    screenOf();

    await waitFor(() =>
      expect(nav.replace).toHaveBeenCalledWith(
        '/en/dashboard/tools/calendar?view=week&day=2026-11-04&cal=me%40example.org&event=e1',
        { scroll: false }
      )
    );
  });

  it('keeps a calendar whose real id is the alias itself', async () => {
    screenOf();

    await screen.findByRole('article', { name: 'Budget review' });
    expect(nav.replace).not.toHaveBeenCalled();
  });

  it('shows who answered what by an icon and a word, never by colour alone', async () => {
    screenOf();

    const detail = await screen.findByRole('article', { name: 'Budget review' });
    expect(within(detail).getByText('workbench.calendar.organizer')).toBeInTheDocument();
    expect(within(detail).getByText('workbench.calendar.responses.declined')).toBeInTheDocument();
    expect(
      within(detail).getByRole('link', { name: 'https://meet.example.org/atlas' })
    ).toHaveAttribute('href', 'https://meet.example.org/atlas');
    expect(
      within(detail).getByRole('link', { name: 'https://docs.example.org/budget' })
    ).toHaveAttribute('href', 'https://docs.example.org/budget');
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

describe('CalendarTool — moving an event', () => {
  function opened(change: Partial<CalendarEventDetail> = {}) {
    nav.search = 'day=2026-11-04&view=week&cal=primary&event=e1';
    const read = api.get.getMockImplementation();
    api.get.mockImplementation((path: string, options?: unknown) =>
      path === '/workbench/calendar/event'
        ? Promise.resolve({ ...DETAIL, ...change })
        : read?.(path, options)
    );
    return screenOf();
  }

  const moveIcon = () => screen.findByRole('button', { name: 'workbench.calendar.move_to' });
  const moving = () => screen.findByRole('menuitem', { name: 'workbench.calendar.move_to_name' });
  const edited = () => screen.findByRole('button', { name: 'workbench.calendar.edit' });
  const series = () => screen.findByRole('button', { name: 'workbench.calendar.edit_series' });
  const noMove = () => screen.queryByRole('button', { name: 'workbench.calendar.move_to' });

  it('sends the event to the calendar picked, closes it and says where it went', async () => {
    api.post.mockResolvedValue(DETAIL);
    const { user } = opened();

    await user.click(await moveIcon());
    await user.click(await moving());

    await waitFor(() => expect(api.post).toHaveBeenCalled());
    const [path, body] = api.post.mock.calls[0]!;
    expect(path).toBe('/workbench/calendar/events/move');
    expect(body).toEqual({ calendar_id: 'primary', event_id: 'e1', destination_id: 'family' });
    await waitFor(() => expect(toast.success).toHaveBeenCalledWith('workbench.calendar.moved_to'));
    expect(String(nav.replace.mock.calls.at(-1)?.[0])).not.toContain('event=');
  });

  it('says an event left in both calendars, and reads the view again', async () => {
    api.post.mockRejectedValue(
      new ApiError('refused', 409, { detail: { code: 'event_left_behind' } })
    );
    const { user } = opened();

    await user.click(await moveIcon());
    await user.click(await moving());

    await waitFor(() =>
      expect(toast.error).toHaveBeenCalledWith('workbench.errors.event_left_behind')
    );
    await waitFor(() => expect(windowCalls().length).toBeGreaterThan(1));
  });

  it('offers a whole series beside the occurrence, and opens on it', async () => {
    const { user } = opened({ recurring: true });

    await user.click(await series());

    expect(await screen.findByText('workbench.calendar.editor.title_series')).toBeInTheDocument();
    expect(screen.getByText('workbench.calendar.editor.repeat')).toBeInTheDocument();
  });

  it('offers the whole series alone where one occurrence cannot change', async () => {
    features = ['all_day', 'event_move', 'calendar_management'];
    opened({ recurring: true });

    await series();
    expect(screen.queryByRole('button', { name: 'workbench.calendar.edit' })).toBeNull();
    expect(screen.getByRole('button', { name: 'workbench.calendar.delete' })).toBeInTheDocument();
  });

  it('sends the deletion of a whole series as one', async () => {
    api.delete.mockResolvedValue(undefined);
    const { user } = opened({ recurring: true });

    await user.click(await screen.findByRole('button', { name: 'workbench.calendar.delete' }));
    await user.click(await screen.findByRole('radio', { name: 'workbench.calendar.delete_whole' }));
    const dialog = screen.getByRole('dialog');
    await user.click(within(dialog).getByRole('button', { name: 'workbench.calendar.delete' }));

    await waitFor(() => expect(api.delete).toHaveBeenCalled());
    expect(api.delete.mock.calls[0][1].params).toMatchObject({ scope: 'series' });
  });

  it('offers no series on an event that is none', async () => {
    opened({ recurring: false });

    await moveIcon();
    expect(screen.queryByRole('button', { name: 'workbench.calendar.edit_series' })).toBeNull();
  });

  it('offers no move of a series', async () => {
    opened({ recurring: true });

    await series();
    expect(noMove()).not.toBeInTheDocument();
  });

  it('offers no move of an invitation: the event is the organiser’s', async () => {
    opened({ my_response: 'accepted' });

    await edited();

    expect(noMove()).not.toBeInTheDocument();
  });

  it('moves an event with guests only where the provider moves rather than copies', async () => {
    const guests = [{ email: 'ana@example.org', name: null, response: 'accepted' as const }];
    const { unmount } = opened({ attendees: guests });
    expect(await moveIcon()).toBeInTheDocument();
    unmount();

    features = GRAPH;
    opened({ attendees: guests });

    await edited();
    expect(noMove()).not.toBeInTheDocument();
  });

  it('offers no move where nothing else can be written', async () => {
    const read = api.get.getMockImplementation();
    api.get.mockImplementation((path: string, options?: unknown) =>
      path === '/workbench/calendar/calendars'
        ? Promise.resolve({
            calendars: [CALENDARS[0], { ...CALENDARS[1], writable: false }],
          })
        : read?.(path, options)
    );
    opened();

    await edited();

    expect(noMove()).not.toBeInTheDocument();
  });
});

describe('CalendarTool — managing calendars', () => {
  const manage = () => screen.findByRole('button', { name: 'workbench.calendar.manage_calendars' });

  it('lists the person’s own calendars and nothing the provider keeps', async () => {
    const { user } = screenOf();

    await user.click(await manage());

    const dialog = await screen.findByRole('dialog');
    expect(within(dialog).getByText('Family')).toBeInTheDocument();
    expect(within(dialog).queryByText('Work')).not.toBeInTheDocument();
  });

  it('creates a calendar once and reads the calendars again', async () => {
    api.post.mockResolvedValue(CALENDARS[1]);
    const { user } = screenOf();
    await user.click(await manage());
    const before = api.get.mock.calls.filter(
      ([path]) => path === '/workbench/calendar/calendars'
    ).length;

    await user.type(await screen.findByLabelText('workbench.calendar.manager.new'), '  Trips  ');
    await user.click(screen.getByRole('button', { name: 'workbench.calendar.manager.create' }));

    await waitFor(() => expect(api.post).toHaveBeenCalledTimes(1));
    const [path, body] = api.post.mock.calls[0]!;
    expect(path).toBe('/workbench/calendar/calendars');
    expect(body).toMatchObject({ name: 'Trips', idempotency_key: expect.any(String) });
    await waitFor(() =>
      expect(
        api.get.mock.calls.filter(([read]) => read === '/workbench/calendar/calendars').length
      ).toBeGreaterThan(before)
    );
  });

  it('deletes a calendar once confirmed, its name in the request', async () => {
    api.delete.mockResolvedValue(undefined);
    const { user } = screenOf();
    await user.click(await manage());

    await user.click(
      await screen.findByRole('button', { name: 'workbench.calendar.manager.delete' })
    );
    await answerConfirmDialog(user);

    await waitFor(() => expect(api.delete).toHaveBeenCalled());
    const [path, options] = api.delete.mock.calls[0]!;
    expect(path).toBe('/workbench/calendar/calendars');
    expect(options).toMatchObject({ params: { calendar_id: 'family' } });
  });

  it('says a refusal and keeps what was typed', async () => {
    api.post.mockRejectedValue(new ApiError('refused', 409, { detail: { code: 'name_taken' } }));
    const { user } = screenOf();
    await user.click(await manage());

    const field = await screen.findByLabelText('workbench.calendar.manager.new');
    await user.type(field, 'Family');
    await user.click(screen.getByRole('button', { name: 'workbench.calendar.manager.create' }));

    await waitFor(() => expect(toast.error).toHaveBeenCalledWith('workbench.errors.name_taken'));
    expect(field).toHaveValue('Family');
  });

  it('offers nothing where the provider does not', async () => {
    features = ['all_day'];
    screenOf();

    await screen.findByRole('link', { name: /Budget review/ });

    expect(
      screen.queryByRole('button', { name: 'workbench.calendar.manage_calendars' })
    ).not.toBeInTheDocument();
  });
});

describe('CalendarTool — the dated tasks', () => {
  const DUE: DueTasks = {
    tasks: [{ id: 't1', list_id: 'home', title: 'Pay rent', due: '2026-11-04' }],
    truncated: false,
    failed: [],
  };

  function withTasks(due: DueTasks | Error = DUE) {
    const answer = rail(features);
    answer.tools.push({
      tool: 'tasks',
      state: 'ready',
      provider: 'google_tasks',
      features: [],
      bounds: {},
    });
    const read = api.get.getMockImplementation();
    api.get.mockImplementation((path: string, options?: unknown) => {
      if (path === '/workbench') return Promise.resolve(answer);
      if (path === '/workbench/tasks/due') {
        return due instanceof Error ? Promise.reject(due) : Promise.resolve(due);
      }
      return read?.(path, options);
    });
    return screenOf();
  }

  const dueCalls = () => api.get.mock.calls.filter(([path]) => path === '/workbench/tasks/due');

  it('draws a task on its day, a link into the tasks', async () => {
    withTasks();

    const task = await screen.findByRole('link', { name: /workbench.calendar.due_task/ });

    expect(task).toHaveAttribute('href', '/en/dashboard/tools/tasks?list=home&task=t1');
    const asked = dueCalls().at(-1)?.[1] as { params: Record<string, unknown> };
    expect(asked.params).toEqual({ start: '2026-11-01', end: '2026-11-07' });
  });

  it('asks nothing where the account has no tasks to draw', async () => {
    screenOf();

    await screen.findByRole('link', { name: /Budget review/ });

    expect(dueCalls()).toHaveLength(0);
    expect(screen.queryByText('workbench.calendar.due_tasks_layer')).not.toBeInTheDocument();
  });

  it('hides the tasks on this device, and reads them no more', async () => {
    const { user } = withTasks();
    await screen.findByRole('link', { name: /workbench.calendar.due_task/ });

    await user.click(screen.getByRole('checkbox', { name: /due_tasks_layer/ }));

    await waitFor(() =>
      expect(
        screen.queryByRole('link', { name: /workbench.calendar.due_task/ })
      ).not.toBeInTheDocument()
    );
    expect(window.localStorage.length).toBeGreaterThan(0);
  });

  it('says tasks could not be read, the events still drawn', async () => {
    withTasks(new Error('down'));

    await screen.findByRole('link', { name: /Budget review/ });

    expect(await screen.findByText('workbench.calendar.due_tasks_failed')).toBeInTheDocument();
  });

  it('says a list could not be read, and a cut', async () => {
    withTasks({ ...DUE, failed: ['home'], truncated: true });

    await screen.findByRole('link', { name: /workbench.calendar.due_task/ });

    expect(await screen.findByText('workbench.calendar.due_tasks_failed')).toBeInTheDocument();
    expect(screen.getByText('workbench.calendar.due_tasks_truncated')).toBeInTheDocument();
  });
});

describe('CalendarTool — an event’s own zone', () => {
  function setIn(zone: string | null) {
    nav.search = 'day=2026-11-04&view=week&cal=primary&event=e1';
    const read = api.get.getMockImplementation();
    api.get.mockImplementation((path: string, options?: unknown) =>
      path === '/workbench/calendar/event'
        ? Promise.resolve({ ...DETAIL, zone })
        : read?.(path, options)
    );
    return screenOf();
  }

  it('says its time where it was set', async () => {
    setIn('America/New_York');

    expect(await screen.findByText('workbench.calendar.in_its_zone')).toBeInTheDocument();
  });

  it('says nothing of a zone this browser does not know, and still opens', async () => {
    setIn('Mars/Olympus_Mons');

    await screen.findByRole('button', { name: 'workbench.calendar.edit' });

    expect(screen.queryByText('workbench.calendar.in_its_zone')).not.toBeInTheDocument();
  });

  it('says nothing of a zone that is the account’s, or of none', async () => {
    const { unmount } = setIn('Europe/Paris');
    await screen.findByRole('button', { name: 'workbench.calendar.edit' });
    expect(screen.queryByText('workbench.calendar.in_its_zone')).not.toBeInTheDocument();
    unmount();

    setIn(null);
    await screen.findByRole('button', { name: 'workbench.calendar.edit' });
    expect(screen.queryByText('workbench.calendar.in_its_zone')).not.toBeInTheDocument();
  });
});

describe('CalendarTool — an invitation', () => {
  function invited(answer: CalendarEventDetail['my_response']) {
    nav.search = 'day=2026-11-04&view=week&cal=primary&event=e1';
    const read = api.get.getMockImplementation();
    api.get.mockImplementation((path: string, options?: unknown) =>
      path === '/workbench/calendar/event'
        ? Promise.resolve({ ...DETAIL, my_response: answer })
        : read?.(path, options)
    );
    return screenOf();
  }

  it('asks for the person’s answer, the current one stated', async () => {
    invited('tentative');

    const maybe = await screen.findByRole('button', {
      name: 'workbench.calendar.answer_tentative',
    });

    expect(maybe).toHaveAttribute('aria-pressed', 'true');
    expect(
      screen.getByRole('button', { name: 'workbench.calendar.answer_accept' })
    ).toHaveAttribute('aria-pressed', 'false');
  });

  it('sends the answer, and asks nothing of an event with nothing to answer', async () => {
    api.post.mockResolvedValue(undefined);
    const { user, unmount } = invited('needsAction');

    await user.click(
      await screen.findByRole('button', { name: 'workbench.calendar.answer_accept' })
    );

    await waitFor(() => expect(api.post).toHaveBeenCalled());
    const [path, body] = api.post.mock.calls[0]!;
    expect(path).toBe('/workbench/calendar/events/answer');
    expect(body).toEqual({ calendar_id: 'primary', event_id: 'e1', response: 'accepted' });
    unmount();

    invited(null);
    // By its event's name: the pane exists from the first render, empty while the event is read.
    await screen.findByRole('article', { name: 'Budget review' });

    expect(screen.queryByRole('button', { name: 'workbench.calendar.answer_accept' })).toBeNull();
  });

  it('sends no answer the person already gave', async () => {
    const { user } = invited('accepted');

    await user.click(
      await screen.findByRole('button', { name: 'workbench.calendar.answer_accept' })
    );

    expect(api.post).not.toHaveBeenCalled();
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

describe('CalendarTool — a click on a slot', () => {
  afterEach(() => vi.useRealTimers());

  /** A slot of the grid: a pointer's shortcut to « New event », which stays the keyboard's way. */
  function slot(container: HTMLElement, name: string): HTMLElement {
    const found = container.querySelector<HTMLElement>(`[data-slot="${name}"]`);
    if (!found) throw new Error(`no slot ${name}`);
    return found;
  }

  it('opens a new event at that hour on that day', async () => {
    const { container } = screenOf();
    await screen.findByRole('link', { name: /Budget review/ });

    const cell = slot(container, '2026-11-03T14');
    cell.getBoundingClientRect = () => ({ top: 100, height: 48 }) as DOMRect;
    fireEvent.click(cell, { clientY: 110, detail: 1 });

    expect(await screen.findByLabelText('workbench.calendar.editor.start_time')).toHaveValue(
      '14:00'
    );
    expect(screen.getByLabelText('workbench.calendar.editor.end_time')).toHaveValue('15:00');
    expect(screen.getByLabelText('workbench.calendar.editor.start')).toHaveValue('2026-11-03');
  });

  it('reads the lower half of the hour as half past', async () => {
    const { container } = screenOf();
    await screen.findByRole('link', { name: /Budget review/ });
    const cell = slot(container, '2026-11-03T14');
    cell.getBoundingClientRect = () => ({ top: 100, height: 48 }) as DOMRect;

    fireEvent.click(cell, { clientY: 130, detail: 1 });

    expect(await screen.findByLabelText('workbench.calendar.editor.start_time')).toHaveValue(
      '14:30'
    );
  });

  it('opens an all-day event from the all-day row', async () => {
    const { container } = screenOf();
    await screen.findByRole('link', { name: /Budget review/ });

    fireEvent.click(slot(container, '2026-11-05'));

    expect(await screen.findByLabelText('workbench.calendar.editor.first_day')).toHaveValue(
      '2026-11-05'
    );
    expect(screen.getByLabelText('workbench.calendar.editor.last_day')).toHaveValue('2026-11-05');
  });

  it('opens a new event from an empty part of a month day', async () => {
    vi.setSystemTime(new Date('2026-11-03T12:00:00Z'));
    nav.search = 'day=2026-11-04&view=month';
    const { container } = screenOf();
    await screen.findByRole('grid', { name: 'workbench.calendar.views.month' });

    fireEvent.click(slot(container, '2026-11-20'));

    expect(await screen.findByLabelText('workbench.calendar.editor.start')).toHaveValue(
      '2026-11-20'
    );
    expect(screen.getByLabelText('workbench.calendar.editor.start_time')).toHaveValue('09:00');
  });

  it('offers no slot where no calendar can be written', async () => {
    api.get.mockImplementation((path: string) => {
      if (path === '/workbench') return Promise.resolve(rail(features));
      if (path === '/workbench/calendar/calendars') {
        return Promise.resolve({
          calendars: CALENDARS.map(calendar => ({ ...calendar, writable: false })),
        });
      }
      if (path === '/workbench/calendar/events') return Promise.resolve(windowAnswer);
      return Promise.resolve({});
    });
    const { container } = screenOf();
    await screen.findByRole('link', { name: /Budget review/ });

    expect(container.querySelector('[data-slot]')).toBeNull();
  });
});

describe('CalendarTool — the day', () => {
  it('reads one day and steps a day at a time', async () => {
    nav.search = 'day=2026-11-02&view=day';
    const { user } = screenOf();

    expect(await screen.findByRole('link', { name: /Budget review/ })).toBeInTheDocument();
    expect(windowCalls().at(-1)).toMatchObject({ start: '2026-11-02', end: '2026-11-02' });

    await user.click(screen.getByRole('button', { name: 'workbench.calendar.next_day' }));
    expect(nav.replace).toHaveBeenLastCalledWith(
      '/en/dashboard/tools/calendar?view=day&day=2026-11-03',
      { scroll: false }
    );
    await user.click(screen.getByRole('button', { name: 'workbench.calendar.previous_day' }));
    expect(nav.replace).toHaveBeenLastCalledWith(
      '/en/dashboard/tools/calendar?view=day&day=2026-11-01',
      { scroll: false }
    );
  });

  it('is offered with the other views', async () => {
    screenOf();

    expect(
      await screen.findByRole('button', { name: 'workbench.calendar.views.day' })
    ).toBeInTheDocument();
  });
});

describe('CalendarTool — the now line', () => {
  afterEach(() => vi.useRealTimers());

  it('marks the time on today’s column, at the account’s wall', async () => {
    vi.useFakeTimers({ toFake: ['Date'] });
    vi.setSystemTime(new Date('2026-11-04T09:30:00Z'));
    const { container } = screenOf();
    await screen.findByRole('link', { name: /Budget review/ });

    const line = container.querySelector<HTMLElement>('[data-now-line]');
    // 10:30 in Paris: ten and a half hours of 48 px.
    expect(line?.style.top).toBe('504px');
    expect(container.querySelectorAll('[data-now-line]')).toHaveLength(1);
  });

  it('draws none on a week that does not hold today', async () => {
    vi.useFakeTimers({ toFake: ['Date'] });
    vi.setSystemTime(new Date('2026-12-20T09:30:00Z'));
    const { container } = screenOf();
    await screen.findByRole('link', { name: /Budget review/ });

    expect(container.querySelector('[data-now-line]')).toBeNull();
  });
});

describe('CalendarTool — the agenda', () => {
  it('reads thirty days from the day shown, and steps by as much', async () => {
    nav.search = 'day=2026-11-02&view=agenda';
    const { user } = screenOf();

    expect(await screen.findByRole('link', { name: /Budget review/ })).toBeInTheDocument();
    expect(windowCalls().at(-1)).toMatchObject({ start: '2026-11-02', end: '2026-12-01' });

    await user.click(screen.getByRole('button', { name: 'workbench.calendar.later_days' }));
    expect(nav.replace).toHaveBeenLastCalledWith(
      '/en/dashboard/tools/calendar?view=agenda&day=2026-12-02',
      { scroll: false }
    );
    await user.click(screen.getByRole('button', { name: 'workbench.calendar.earlier_days' }));
    expect(nav.replace).toHaveBeenLastCalledWith(
      '/en/dashboard/tools/calendar?view=agenda&day=2026-10-03',
      { scroll: false }
    );
  });
});

describe('CalendarTool — what a chip says', () => {
  const inPrimary = (...events: CalendarEvent[]): CalendarEventsWindow => ({
    calendars: [{ calendar_id: 'primary', events, truncated: false, skipped: 0, error: null }],
  });

  it('joins the call from the chip, in a tab of its own', async () => {
    windowAnswer = inPrimary(
      event('c1', { summary: 'Standup', conference_url: 'https://meet.google.com/abc-defg-hij' })
    );
    screenOf();

    const join = await screen.findByRole('link', { name: /workbench.calendar.join_call/ });
    expect(join).toHaveAttribute('href', 'https://meet.google.com/abc-defg-hij');
    expect(join).toHaveAttribute('target', '_blank');
    expect(join).toHaveAttribute('rel', 'noopener noreferrer');
  });

  it('offers no call an address it would not follow', async () => {
    windowAnswer = inPrimary(
      event('c2', { summary: 'Trap', conference_url: 'javascript:alert(1)' })
    );
    screenOf();
    await screen.findByRole('link', { name: /Trap/ });

    expect(screen.queryByRole('link', { name: /workbench.calendar.join_call/ })).toBeNull();
  });

  it('says an occurrence belongs to a series', async () => {
    windowAnswer = inPrimary(event('s1', { summary: 'Weekly', recurring: true }));
    screenOf();

    const chip = await screen.findByRole('link', { name: /Weekly/ });
    expect(within(chip).getByText('workbench.calendar.series')).toBeInTheDocument();
  });
});

describe('CalendarTool — duplicating an event', () => {
  it('opens a new event holding what the event says, under a key of its own', async () => {
    nav.search = 'day=2026-11-02&view=week&cal=primary&event=e1';
    const { user } = screenOf();

    await user.click(await screen.findByRole('button', { name: 'workbench.calendar.duplicate' }));

    expect(await screen.findByLabelText('workbench.calendar.editor.summary')).toHaveValue(
      'Budget review'
    );
    await user.click(screen.getByRole('button', { name: 'workbench.calendar.editor.create' }));
    await waitFor(() => expect(api.post).toHaveBeenCalled());
    const [, body] = api.post.mock.calls[0];
    expect(body).toMatchObject({
      calendar_id: 'primary',
      summary: 'Budget review',
      attendees: ['ana@example.org', 'theo@example.org'],
    });
  });

  it('is offered on a calendar that cannot be written, into one that can', async () => {
    api.get.mockImplementation((path: string) => {
      if (path === '/workbench') return Promise.resolve(rail(features));
      if (path === '/workbench/calendar/calendars') {
        return Promise.resolve({
          calendars: [{ ...CALENDARS[0], writable: false }, CALENDARS[1]],
        });
      }
      if (path === '/workbench/calendar/events') return Promise.resolve(windowAnswer);
      if (path === '/workbench/calendar/event') return Promise.resolve(DETAIL);
      return Promise.resolve({});
    });
    nav.search = 'day=2026-11-02&view=week&cal=primary&event=e1';
    const { user } = screenOf();

    expect(await screen.findByText('Budget review', { selector: 'h2' })).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'workbench.calendar.edit' })).toBeNull();
    await user.click(screen.getByRole('button', { name: 'workbench.calendar.duplicate' }));
    await user.click(
      await screen.findByRole('button', { name: 'workbench.calendar.editor.create' })
    );

    await waitFor(() => expect(api.post).toHaveBeenCalled());
    expect(api.post.mock.calls[0][1]).toMatchObject({ calendar_id: 'family' });
  });
});

describe('CalendarTool — the month on a phone', () => {
  it('shows the days in reach of a thumb and the picked day’s events below', async () => {
    media.phone = true;
    media.wide = false;
    nav.search = 'day=2026-11-02&view=month';
    const { user } = screenOf();

    // The name says what the day holds; the small month, hidden on a phone, only its date.
    const day = await screen.findByRole('button', { name: /^Monday, November 2, / });
    expect(day).toHaveAttribute('aria-pressed', 'true');
    expect(await screen.findByRole('link', { name: /Budget review/ })).toBeInTheDocument();

    await user.click(screen.getByRole('button', { name: /^Tuesday, November 10, / }));
    expect(nav.replace).toHaveBeenLastCalledWith(
      '/en/dashboard/tools/calendar?view=month&day=2026-11-10',
      { scroll: false }
    );
  });
});

describe('CalendarTool — its keys', () => {
  const press = (key: string) => fireEvent.keyDown(window, { key });

  it('opens a new event on « n »', async () => {
    screenOf();
    await screen.findByRole('link', { name: /Budget review/ });

    press('n');

    expect(await screen.findByLabelText('workbench.calendar.editor.summary')).toBeInTheDocument();
  });

  it('changes the view on its first letter', async () => {
    screenOf();
    await screen.findByRole('link', { name: /Budget review/ });

    press('m');

    expect(nav.replace).toHaveBeenLastCalledWith(
      '/en/dashboard/tools/calendar?view=month&day=2026-11-04',
      { scroll: false }
    );
  });

  it('moves as far as the view reaches', async () => {
    screenOf();
    await screen.findByRole('link', { name: /Budget review/ });

    press('j');

    expect(nav.replace).toHaveBeenLastCalledWith(
      '/en/dashboard/tools/calendar?view=week&day=2026-11-11',
      { scroll: false }
    );
  });
});

describe('CalendarTool — what another tool hands it', () => {
  it('opens a new event holding what it was given', async () => {
    handOff('owner', { kind: 'event', summary: 'Budget', description: 'From a message' });
    screenOf();

    expect(await screen.findByLabelText('workbench.calendar.editor.summary')).toHaveValue('Budget');
    expect(screen.getByLabelText('workbench.calendar.editor.description')).toHaveValue(
      'From a message'
    );
  });

  it('opens with the video call ticked where LIA read one asked for and no link given', async () => {
    handOff('owner', {
      kind: 'event',
      summary: 'Call with Ana',
      description: 'From a message',
      proposal: {
        summary: 'Call with Ana',
        start_date: '2026-11-12',
        start_time: '10:00',
        end_date: null,
        end_time: null,
        all_day: false,
        location: '',
        description: 'From a message',
        attendees: ['ana@example.org'],
        repeat: 'none',
        conference: true,
      },
    });
    screenOf();

    expect(await screen.findByLabelText('workbench.calendar.editor.conference')).toBeChecked();
  });
});

describe('CalendarTool — panes sized by hand', () => {
  it('names its separator and drives the pane it sits beside, back to the layout on Enter', async () => {
    screenOf();
    await screen.findByRole('link', { name: /Budget review/ });
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

beforeEach(() => {
  setHandoffOwner(null);
  setHandoffOwner('owner');
});
