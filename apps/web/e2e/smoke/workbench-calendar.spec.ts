/**
 * The « Tools » calendar screen, hermetic (ADR-369, Tasks 5.2 and 5b.1).
 *
 * The API is played by the spec: one ready Google calendar provider, two
 * calendars, a timed event, an all-day event and an occurrence of a series
 * with a video call. Proven in the three views — week at 1280 light, month at
 * 1280 dark, agenda at 390 OLED: no horizontal scroll, axe clean on the screen;
 * an occurrence opens in the detail and says a change reaches it alone; the
 * keyboard opens an event and gets its link back when it closes.
 */
import AxeBuilder from '@axe-core/playwright';
import type { Page, Route } from '@playwright/test';

import { test, expect, waitForHydration } from '../fixtures';
import type { MockRoute } from '../fixtures/api-mock';
import { appConfig } from '../fixtures/dashboard-shell';
import { expectNoOverflow, prepareTheme } from './overflow-report';
import {
  boxOf,
  expectInside,
  expectLinesCentredIn,
  expectNoZoomOnFocus,
  expectOnOneLine,
  expectSameEnd,
  expectSameStart,
  expectStackedWhole,
  expectUnder,
} from './phone-lines';

const TODAY = new Intl.DateTimeFormat('en-CA', {
  timeZone: 'Europe/Paris',
  year: 'numeric',
  month: '2-digit',
  day: '2-digit',
}).format(new Date());

function shifted(days: number): string {
  const day = new Date(`${TODAY}T12:00:00Z`);
  day.setUTCDate(day.getUTCDate() + days);
  return day.toISOString().slice(0, 10);
}

const RAIL = {
  tools: ['mail', 'calendar', 'tasks', 'contacts', 'files', 'lights'].map(tool =>
    tool === 'calendar'
      ? {
          tool,
          state: 'ready',
          provider: 'google_calendar',
          features: [
            'all_day',
            'conference',
            'notify_attendees',
            'occurrence_edit',
            'event_move',
            'event_move_with_guests',
            'calendar_management',
          ],
          bounds: {
            summary_max_chars: 1024,
            series_max_count: 730,
            location_max_chars: 1024,
            description_max_chars: 8192,
            attendees_max: 100,
            recipient_query_min_chars: 2,
          },
        }
      : { tool, state: 'not_connected', provider: null, features: [], bounds: {} }
  ),
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

const CALENDARS = [
  {
    id: 'primary',
    name: 'Ana Lima',
    color: '#7c3aed',
    primary: true,
    writable: true,
    manageable: false,
  },
  { id: 'team', name: 'Team', color: '#059669', primary: false, writable: true, manageable: true },
];

/** A name as long as a person may give a calendar: what a list of places must hold. */
const LONG_NAMED = {
  id: 'club',
  name: 'The neighbourhood sports association shared calendar for the whole season',
  color: '#b45309',
  primary: false,
  writable: true,
  manageable: true,
};

/** What an event says when it is read whole, beyond what a view draws. */
const WHOLE = {
  description: null,
  attendees: [],
  organizer: null,
  link: null,
  reminder_minutes: null,
  busy: true,
  private: false,
  zone: null,
  my_response: null,
};

// Midday in UTC: the same local day in Paris whatever the season.
const EVENTS = [
  {
    id: 'e1',
    calendar_id: 'primary',
    summary: 'Committee review',
    all_day: false,
    start: `${TODAY}T11:00:00Z`,
    end: `${TODAY}T12:00:00Z`,
    location: 'Room 4',
    recurring: false,
    conference_url: null,
  },
  {
    id: 'e2',
    calendar_id: 'team',
    summary: 'Team offsite',
    all_day: true,
    start: TODAY,
    end: shifted(1),
    location: null,
    recurring: false,
    conference_url: null,
  },
  {
    id: 'e3_20261101',
    calendar_id: 'primary',
    summary: 'Weekly sync',
    all_day: false,
    start: `${TODAY}T15:00:00Z`,
    end: `${TODAY}T15:30:00Z`,
    location: null,
    recurring: true,
    conference_url: 'https://meet.google.com/abc-defg-hij',
  },
];

async function answer(route: Route): Promise<void> {
  const url = new URL(route.request().url());
  if (url.pathname.endsWith('/calendar/calendars')) {
    await route.fulfill({ json: { calendars: CALENDARS } });
    return;
  }
  if (url.pathname.endsWith('/calendar/events')) {
    await route.fulfill({
      json: {
        calendars: CALENDARS.map(calendar => ({
          calendar_id: calendar.id,
          events: EVENTS.filter(event => event.calendar_id === calendar.id),
          truncated: false,
          skipped: 0,
          error: null,
        })),
      },
    });
    return;
  }
  // The page names the event as the route reads it: `calendar_id` + `event_id`.
  const event = EVENTS.find(item => item.id === url.searchParams.get('event_id')) ?? EVENTS[0];
  await route.fulfill({ json: { ...event, ...WHOLE } });
}

async function playTheApi(
  mockApi: (routes: MockRoute[]) => Promise<void>,
  extra: MockRoute[] = [],
  assists = false
) {
  await mockApi([
    {
      url: '**/api/v1/config',
      json: {
        ...appConfig,
        features: {
          ...appConfig.features,
          workbench_enabled: true,
          tool_assists_enabled: assists,
        },
        capabilities: {
          workbench: { enabled: true, family: 'work' },
          tool_assists: { enabled: assists, family: 'work' },
        },
      },
    },
    { url: '**/api/v1/workbench', json: RAIL },
    { url: '**/api/v1/workbench/calendar/**', method: 'GET', handler: answer },
    ...extra,
  ]);
}

for (const sample of [
  { width: 1280, theme: 'light', view: 'week' },
  { width: 1280, theme: 'dark', view: 'month' },
  { width: 390, theme: 'oled', view: 'agenda' },
] as const) {
  test(`calendar ${sample.view} at ${sample.width}px in ${sample.theme}`, async ({
    page,
    authenticate,
    mockApi,
  }) => {
    await page.setViewportSize({ width: sample.width, height: 900 });
    await prepareTheme(page, sample.theme);
    await authenticate({ timezone: 'Europe/Paris' });
    await playTheApi(mockApi);

    await page.goto(`/en/dashboard/tools/calendar?view=${sample.view}&day=${TODAY}`);
    await waitForHydration(page, 'button');
    await expect(page.getByText('Committee review').first()).toBeVisible();

    await expectNoOverflow(page, `${sample.view} ${sample.width}px ${sample.theme}`);
    const scan = await new AxeBuilder({ page }).include('main').analyze();
    expect(scan.violations).toEqual([]);
  });
}

/** The wall time of an instant in the account's zone, as the page sends it. */
function wall(instant: string): string {
  const parts = new Intl.DateTimeFormat('en-GB', {
    timeZone: 'Europe/Paris',
    hour: '2-digit',
    minute: '2-digit',
  }).format(new Date(instant));
  return `${TODAY}T${parts}`;
}

function later(time: string, hours: number): string {
  const [day, clock] = time.split('T');
  const [hour, minute] = clock.split(':');
  return `${day}T${String(Number(hour) + hours).padStart(2, '0')}:${minute}`;
}

/** The chip of an event, in the middle of the grid: an edge would scroll under the drag. */
async function chipOf(page: Page, name: RegExp) {
  const chip = page.getByRole('link', { name });
  await chip.evaluate(element => element.scrollIntoView({ block: 'center' }));
  return chip;
}

/** Holds the mouse on a point, travels, lets go: a drag as a hand makes it. */
async function drag(
  page: Page,
  from: { x: number; y: number },
  by: { x: number; y: number }
): Promise<void> {
  await page.mouse.move(from.x, from.y);
  await page.mouse.down();
  await page.mouse.move(from.x + by.x, from.y + by.y, { steps: 12 });
  await page.mouse.up();
}

test('an event dragged an hour down moves there, undone from the toast, a click staying a click', async ({
  page,
  authenticate,
  mockApi,
}) => {
  await page.setViewportSize({ width: 1280, height: 900 });
  await authenticate({ timezone: 'Europe/Paris' });
  const patches: Record<string, unknown>[] = [];
  await playTheApi(mockApi, [
    {
      url: '**/api/v1/workbench/calendar/events',
      method: 'PATCH',
      handler: async route => {
        patches.push(route.request().postDataJSON());
        await route.fulfill({ json: { ...EVENTS[0], ...WHOLE } });
      },
    },
  ]);

  await page.goto(`/en/dashboard/tools/calendar?view=week&day=${TODAY}`);
  await waitForHydration(page, 'button');
  const chip = await chipOf(page, /^Committee review/);
  const box = await chip.boundingBox();
  if (!box) throw new Error('the chip has no box');

  await drag(page, { x: box.x + box.width / 2, y: box.y + 8 }, { x: 0, y: 48 });

  const start = wall(EVENTS[0].start);
  await expect.poll(() => patches.length).toBe(1);
  expect(patches[0]).toMatchObject({
    event_id: 'e1',
    start: later(start, 1),
    end: later(start, 2),
    timezone: 'Europe/Paris',
  });
  // The click a drag ends on opens nothing.
  expect(page.url()).not.toContain('event=');

  await page.getByRole('button', { name: 'Undo' }).click();
  await expect.poll(() => patches.length).toBe(2);
  expect(patches[1]).toMatchObject({ start, end: later(start, 1) });

  await chip.click();
  await expect(page).toHaveURL(/event=e1/);
});

test('an event stretched by its bottom edge keeps its start', async ({
  page,
  authenticate,
  mockApi,
}) => {
  await page.setViewportSize({ width: 1280, height: 900 });
  await authenticate({ timezone: 'Europe/Paris' });
  const patches: Record<string, unknown>[] = [];
  await playTheApi(mockApi, [
    {
      url: '**/api/v1/workbench/calendar/events',
      method: 'PATCH',
      handler: async route => {
        patches.push(route.request().postDataJSON());
        await route.fulfill({ json: { ...EVENTS[0], ...WHOLE } });
      },
    },
  ]);

  await page.goto(`/en/dashboard/tools/calendar?view=week&day=${TODAY}`);
  await waitForHydration(page, 'button');
  const chip = await chipOf(page, /^Committee review/);
  const edge = chip.locator('xpath=..').locator('[data-chip-resize]');
  const box = await edge.boundingBox();
  if (!box) throw new Error('the edge has no box');

  await drag(page, { x: box.x + box.width / 2, y: box.y + box.height / 2 }, { x: 0, y: 48 });

  const start = wall(EVENTS[0].start);
  await expect.poll(() => patches.length).toBe(1);
  expect(patches[0]).toMatchObject({ start, end: later(start, 2) });
});

test('nobody is told by a slip of the mouse: guests open the editor, nothing leaves', async ({
  page,
  authenticate,
  mockApi,
}) => {
  await page.setViewportSize({ width: 1280, height: 900 });
  await authenticate({ timezone: 'Europe/Paris' });
  let patched = 0;
  await playTheApi(mockApi, [
    {
      url: '**/api/v1/workbench/calendar/event?*',
      method: 'GET',
      handler: route =>
        route.fulfill({
          json: {
            ...EVENTS[0],
            ...WHOLE,
            attendees: [{ email: 'ana@example.org', name: null, response: 'accepted' }],
          },
        }),
    },
    {
      url: '**/api/v1/workbench/calendar/events',
      method: 'PATCH',
      handler: async route => {
        patched += 1;
        await route.fulfill({ json: {} });
      },
    },
  ]);

  await page.goto(`/en/dashboard/tools/calendar?view=week&day=${TODAY}`);
  await waitForHydration(page, 'button');
  const chip = await chipOf(page, /^Committee review/);
  const box = await chip.boundingBox();
  if (!box) throw new Error('the chip has no box');

  await drag(page, { x: box.x + box.width / 2, y: box.y + 8 }, { x: 0, y: 48 });

  const editor = page.getByRole('dialog');
  await expect(editor.getByLabel('Start time')).toHaveValue(
    later(wall(EVENTS[0].start), 1).slice(-5)
  );
  await expect(editor.getByText('Tell the guests')).toBeVisible();
  expect(patched).toBe(0);
});

test('a click on a slot opens a new event at that hour', async ({
  page,
  authenticate,
  mockApi,
}) => {
  await page.setViewportSize({ width: 1280, height: 900 });
  await authenticate({ timezone: 'Europe/Paris' });
  await playTheApi(mockApi);

  await page.goto(`/en/dashboard/tools/calendar?view=day&day=${shifted(1)}`);
  await waitForHydration(page, 'button');
  await page.locator(`[data-slot="${shifted(1)}T14"]`).click({ position: { x: 40, y: 8 } });

  const editor = page.getByRole('dialog');
  await expect(editor.getByLabel('Start time')).toHaveValue('14:00');
});

test('the month on a phone reads on its own width, the day picked listed below', async ({
  page,
  authenticate,
  mockApi,
}) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await authenticate({ timezone: 'Europe/Paris' });
  await playTheApi(mockApi);

  await page.goto(`/en/dashboard/tools/calendar?view=month&day=${TODAY}`);
  await waitForHydration(page, 'button');

  await expect(page.getByRole('link', { name: /Committee review/ })).toBeVisible();
  await expectNoOverflow(page, 'month at 390px');
  const scan = await new AxeBuilder({ page }).include('main').analyze();
  expect(scan.violations).toEqual([]);
});

test('an occurrence opens in the detail and says a change reaches it alone', async ({
  page,
  authenticate,
  mockApi,
}) => {
  await page.setViewportSize({ width: 1280, height: 900 });
  await authenticate({ timezone: 'Europe/Paris' });
  await playTheApi(mockApi);

  await page.goto(`/en/dashboard/tools/calendar?view=agenda&day=${TODAY}`);
  await waitForHydration(page, 'button');
  await page.getByRole('link').filter({ hasText: 'Weekly sync' }).first().click();

  const detail = page.getByRole('article', { name: 'Weekly sync' });
  await expect(detail.getByText(/reaches this occurrence alone/)).toBeVisible();
  await expect(detail.getByRole('link', { name: 'Join the video call' })).toHaveAttribute(
    'rel',
    /noopener/
  );
});

test('a whole series is asked for: the editor repeats, a deletion says which', async ({
  page,
  authenticate,
  mockApi,
}) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await authenticate({ timezone: 'Europe/Paris' });
  await playTheApi(mockApi);

  await page.goto(`/en/dashboard/tools/calendar?view=agenda&day=${TODAY}`);
  await waitForHydration(page, 'button');
  await page.getByRole('link').filter({ hasText: 'Weekly sync' }).first().click();
  const detail = page.getByRole('article', { name: 'Weekly sync' });

  await detail.getByRole('button', { name: 'Edit the series' }).click();
  const editor = page.getByRole('dialog');
  await expect(editor.getByRole('heading', { name: 'Edit the whole series' })).toBeVisible();
  await expect(editor.getByRole('combobox', { name: 'Repeats' })).toBeVisible();
  await expectNoOverflow(page, 'the series editor at 390px');
  await editor.getByRole('button', { name: 'Cancel' }).click();

  await detail.getByRole('button', { name: 'Delete' }).click();
  const asked = page.getByRole('dialog');
  await expect(asked.getByRole('radio', { name: 'This occurrence' })).toBeChecked();
  await asked.getByRole('radio', { name: 'The whole series' }).check();
  await expect(asked.getByText('Every occurrence of the series is removed.')).toBeVisible();
  const scan = await new AxeBuilder({ page }).include('[role="dialog"]').analyze();
  expect(scan.violations).toEqual([]);
});

test('an invitation is answered from the event, the organiser told', async ({
  page,
  authenticate,
  mockApi,
}) => {
  await page.setViewportSize({ width: 1280, height: 900 });
  await authenticate({ timezone: 'Europe/Paris' });
  const answers: Record<string, unknown>[] = [];
  await playTheApi(mockApi, [
    {
      url: '**/api/v1/workbench/calendar/event?*',
      method: 'GET',
      handler: route =>
        route.fulfill({
          json: {
            ...EVENTS[0],
            ...WHOLE,
            organizer: 'ana@example.org',
            my_response: 'needsAction',
          },
        }),
    },
    {
      url: '**/api/v1/workbench/calendar/events/answer',
      method: 'POST',
      handler: async route => {
        answers.push(route.request().postDataJSON());
        await route.fulfill({ status: 204, body: '' });
      },
    },
  ]);

  await page.goto(`/en/dashboard/tools/calendar?view=agenda&day=${TODAY}`);
  await waitForHydration(page, 'button');
  await page.getByRole('link').filter({ hasText: 'Committee review' }).first().click();

  const detail = page.getByRole('article', { name: 'Committee review' });
  await detail.getByRole('button', { name: 'Accept' }).click();

  await expect.poll(() => answers.length).toBe(1);
  expect(answers[0]).toEqual({ calendar_id: 'primary', event_id: 'e1', response: 'accepted' });
  await expect(detail.getByRole('button', { name: 'Accept' })).toHaveAttribute(
    'aria-pressed',
    'true'
  );
});

test('a search takes the view’s place, and clearing it gives the view back', async ({
  page,
  authenticate,
  mockApi,
}) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await authenticate({ timezone: 'Europe/Paris' });
  await playTheApi(mockApi, [
    {
      url: '**/api/v1/workbench/calendar/search?*',
      method: 'GET',
      json: { events: [EVENTS[0]], truncated: false, failed: ['team'] },
    },
  ]);

  await page.goto(`/en/dashboard/tools/calendar?view=agenda&day=${TODAY}`);
  await waitForHydration(page, 'button');
  await page.getByRole('searchbox').fill('committee');
  await page.getByRole('searchbox').press('Enter');

  const found = page.getByRole('list', { name: 'Events found' });
  await expect(found.getByRole('link', { name: /Committee review/ })).toBeVisible();
  await expect(page.getByText(/could not be read/)).toBeVisible();
  await expect(page.getByRole('link').filter({ hasText: 'Weekly sync' })).toHaveCount(0);
  await expectNoOverflow(page, 'calendar search');

  await page.getByRole('button', { name: 'Back to the calendar' }).click();

  await expect(page.getByRole('link').filter({ hasText: 'Weekly sync' }).first()).toBeVisible();
});

/** The move as the provider answers it, each request kept. */
function movesInto(moves: Record<string, unknown>[]): MockRoute {
  return {
    url: '**/api/v1/workbench/calendar/events/move',
    method: 'POST',
    handler: async route => {
      moves.push(route.request().postDataJSON());
      await route.fulfill({ json: { ...EVENTS[0], ...WHOLE, calendar_id: 'team' } });
    },
  };
}

test('an event goes to another calendar from its detail', async ({
  page,
  authenticate,
  mockApi,
}) => {
  await page.setViewportSize({ width: 1280, height: 900 });
  await authenticate({ timezone: 'Europe/Paris' });
  const moves: Record<string, unknown>[] = [];
  await playTheApi(mockApi, [movesInto(moves)]);

  await page.goto(`/en/dashboard/tools/calendar?view=agenda&day=${TODAY}`);
  await waitForHydration(page, 'button');
  await page.getByRole('link').filter({ hasText: 'Committee review' }).first().click();

  const detail = page.getByRole('article', { name: 'Committee review' });
  await detail.getByRole('button', { name: 'Move to…' }).click();
  expect(moves).toHaveLength(0);
  await page.getByRole('menuitem', { name: 'Move to Team' }).click();

  await expect.poll(() => moves.length).toBe(1);
  expect(moves[0]).toEqual({ calendar_id: 'primary', event_id: 'e1', destination_id: 'team' });
  await expect(page.getByRole('article', { name: 'Committee review' })).toHaveCount(0);
  await expect(page.getByText('Moved to Team')).toBeVisible();
});

test('the keyboard moves an event from its bar, and Escape leaves it where it is', async ({
  page,
  authenticate,
  mockApi,
}) => {
  await page.setViewportSize({ width: 1280, height: 900 });
  await authenticate({ timezone: 'Europe/Paris' });
  const moves: Record<string, unknown>[] = [];
  await playTheApi(mockApi, [movesInto(moves)]);

  await page.goto(`/en/dashboard/tools/calendar?view=agenda&day=${TODAY}`);
  await waitForHydration(page, 'button');
  await page.getByRole('link').filter({ hasText: 'Committee review' }).first().click();

  const move = page
    .getByRole('article', { name: 'Committee review' })
    .getByRole('button', { name: 'Move to…' });
  const line = page.getByRole('menuitem', { name: 'Move to Team' });
  await move.focus();
  await page.keyboard.press('Enter');
  await expect(line).toBeFocused();
  await page.keyboard.press('Escape');
  await expect(move).toBeFocused();
  expect(moves).toHaveLength(0);

  await page.keyboard.press('Enter');
  await expect(line).toBeFocused();
  await page.keyboard.press('Enter');

  await expect.poll(() => moves.length).toBe(1);
  expect(moves[0]).toEqual({ calendar_id: 'primary', event_id: 'e1', destination_id: 'team' });
});

test('a very narrow phone keeps every act of an event whole at larger text', async ({
  page,
  authenticate,
  mockApi,
}) => {
  await page.setViewportSize({ width: 320, height: 700 });
  await authenticate({ timezone: 'Europe/Paris' });
  await playTheApi(mockApi);

  await page.goto(`/en/dashboard/tools/calendar?view=agenda&day=${TODAY}`);
  await waitForHydration(page, 'button');
  await page.getByRole('link').filter({ hasText: 'Committee review' }).first().click();

  const detail = page.getByRole('article', { name: 'Committee review' });
  const acts = detail.getByTestId('detail-acts').getByRole('button');
  await expect(acts).toHaveCount(5);

  // The tool's name gives way, then the icons take another line: an act is never cut.
  for (const size of ['125%', '150%', '200%']) {
    await page.evaluate(value => {
      document.documentElement.style.fontSize = value;
    }, size);
    for (const act of await acts.all()) await expectInside(detail, act);
    await expectInside(detail, detail.getByRole('button', { name: 'Calendar' }));
  }
});

/* AN EVENT'S ACTS: all of them in its bar, on a computer and on a phone (owner, 2026-11-06). */
for (const width of [390, 360, 320]) {
  test(`an event keeps every act on one line at ${width}px, and its list on the screen`, async ({
    page,
    authenticate,
    mockApi,
  }) => {
    await page.setViewportSize({ width, height: 844 });
    await authenticate({ timezone: 'Europe/Paris' });
    await playTheApi(mockApi, [
      {
        url: '**/api/v1/workbench/calendar/calendars',
        method: 'GET',
        json: { calendars: [...CALENDARS, LONG_NAMED] },
      },
    ]);

    await page.goto(`/en/dashboard/tools/calendar?view=agenda&day=${TODAY}`);
    await waitForHydration(page, 'button');
    await page.getByRole('link').filter({ hasText: 'Committee review' }).first().click();

    const detail = page.getByRole('article', { name: 'Committee review' });
    const move = detail.getByRole('button', { name: 'Move to…' });
    const ask = detail.getByRole('button', { name: 'Ask LIA' });
    await expectOnOneLine(
      detail.getByRole('button', { name: 'Calendar' }),
      detail.getByRole('button', { name: 'Edit', exact: true }),
      detail.getByRole('button', { name: 'Duplicate' }),
      move,
      detail.getByRole('button', { name: 'Delete' }),
      ask
    );
    await expectInside(detail, ask);
    await expect(detail.getByRole('button', { name: 'More actions' })).toHaveCount(0);
    await expectNoOverflow(page, `the event's acts at ${width}px`);

    await move.click();
    await expect(page.getByRole('menuitem', { name: 'Move to Team' })).toBeVisible();
    const longest = await boxOf(page.getByRole('menuitem', { name: /sports association/ }));
    expect(longest.x, 'the list starts on the screen').toBeGreaterThanOrEqual(0);
    expect(longest.x + longest.width, 'the list ends on the screen').toBeLessThanOrEqual(width);
    await expectNoOverflow(page, `the calendars an event can go to at ${width}px`);
  });
}

test('a phone manages its calendars from the menu: only the person’s own are listed', async ({
  page,
  authenticate,
  mockApi,
}) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await authenticate({ timezone: 'Europe/Paris' });
  const made: Record<string, unknown>[] = [];
  await playTheApi(mockApi, [
    {
      url: '**/api/v1/workbench/calendar/calendars',
      method: 'POST',
      handler: async route => {
        made.push(route.request().postDataJSON());
        await route.fulfill({ status: 201, json: CALENDARS[1] });
      },
    },
  ]);

  await page.goto(`/en/dashboard/tools/calendar?view=agenda&day=${TODAY}`);
  await waitForHydration(page, 'button');
  await page.getByRole('button', { name: 'Calendars' }).click();
  await page.getByRole('menuitem', { name: 'Manage calendars' }).click();

  const dialog = page.getByRole('dialog', { name: 'Manage calendars' });
  await expect(dialog.getByText('Team')).toBeVisible();
  await expect(dialog.getByText('Ana Lima')).toHaveCount(0);
  await dialog.getByLabel('New calendar').fill('Trips');
  await dialog.getByRole('button', { name: 'Create' }).click();

  await expect.poll(() => made.length).toBe(1);
  expect(made[0]).toMatchObject({ name: 'Trips' });
  await expectNoOverflow(page, 'calendar manager');
});

test('a dated task is drawn on its day and opens among the tasks', async ({
  page,
  authenticate,
  mockApi,
}) => {
  await page.setViewportSize({ width: 1280, height: 900 });
  await authenticate({ timezone: 'Europe/Paris' });
  const rail = {
    ...RAIL,
    tools: RAIL.tools.map(tool =>
      tool.tool === 'tasks' ? { ...tool, state: 'ready', provider: 'google_tasks' } : tool
    ),
  };
  await playTheApi(mockApi, [
    { url: '**/api/v1/workbench', json: rail },
    {
      url: '**/api/v1/workbench/tasks/due?*',
      method: 'GET',
      json: {
        tasks: [{ id: 't1', list_id: 'home', title: 'Pay rent', due: TODAY }],
        truncated: false,
        failed: [],
      },
    },
  ]);

  await page.goto(`/en/dashboard/tools/calendar?view=week&day=${TODAY}`);
  await waitForHydration(page, 'button');

  const task = page.getByRole('link').filter({ hasText: 'Task: Pay rent' }).first();
  await expect(task).toHaveAttribute('href', '/en/dashboard/tools/tasks?list=home&task=t1');

  await page.getByRole('checkbox', { name: 'Dated tasks' }).click();

  await expect(page.getByRole('link').filter({ hasText: 'Task: Pay rent' })).toHaveCount(0);
});

/**
 * Owner request (2026-10-31): a guest is suggested from the account's contacts exactly as a
 * message's recipient is — the same field, the same door, picked with the keyboard.
 */
test.describe('on a touch screen', () => {
  test.use({ hasTouch: true, isMobile: true, viewport: { width: 390, height: 844 } });
  test.skip(({ browserName }) => browserName === 'firefox', 'no mobile emulation');

  /** Owner requests (2026-11-06): the head at the left, LIA beside it, one press per line. */
  test('the editor starts at the left, and takes the thumb without zooming', async ({
    page,
    authenticate,
    mockApi,
  }) => {
    await authenticate({ timezone: 'Europe/Paris' });
    await playTheApi(mockApi, [], true);
    await page.goto(`/en/dashboard/tools/calendar?view=agenda&day=${TODAY}`);
    await waitForHydration(page, 'button');

    await page.getByRole('button', { name: 'New event' }).first().click();
    const editor = page.getByRole('dialog', { name: 'New event' });
    const title = editor.getByRole('heading', { name: 'New event' });
    const line = editor.getByText(/account's clock/);
    await expectSameStart(title, line);
    await expectSameStart(title, editor.getByLabel('Title'));
    await expectOnOneLine(
      title,
      editor.getByRole('button', { name: 'Describe the event in a sentence' })
    );
    await expectStackedWhole(
      editor.getByRole('button', { name: 'Create' }),
      editor.getByRole('button', { name: 'Cancel' })
    );
    await expectNoZoomOnFocus(page);
  });
});

/** Owner report (2026-11-06): the list and its dialog open over the editor's own dialog. */
test('LIA writes a description from inside the editor, the person keeping the last word', async ({
  page,
  authenticate,
  mockApi,
}) => {
  await page.setViewportSize({ width: 1280, height: 900 });
  await authenticate({ timezone: 'Europe/Paris' });
  const asked: unknown[] = [];
  await playTheApi(
    mockApi,
    [
      {
        url: '**/api/v1/tool-assists/text/write',
        method: 'POST',
        handler: async route => {
          asked.push(route.request().postDataJSON());
          await route.fulfill({
            json: {
              text: 'The committee reviews the agenda.',
              subject: null,
              cut: false,
              usage: null,
            },
          });
        },
      },
    ],
    true
  );
  await page.goto(`/en/dashboard/tools/calendar?view=week&day=${TODAY}`);
  await waitForHydration(page, 'button');

  await page.getByRole('button', { name: 'New event' }).first().click();
  const editor = page.getByRole('dialog', { name: 'New event' });
  await editor.getByRole('button', { name: 'Write with LIA' }).click();
  await page.getByRole('menuitem', { name: 'Write from an instruction' }).click();
  const writing = page.getByRole('dialog', { name: 'Write from an instruction' });
  await writing.getByRole('textbox').fill('A short agenda');
  await writing.getByRole('button', { name: 'Propose' }).click();

  await expect(writing.getByText('The committee reviews the agenda.')).toBeVisible();
  expect(asked).toEqual([{ kind: 'event_description', instruction: 'A short agenda' }]);
  await writing.getByRole('button', { name: 'Use this text' }).click();
  await expect(writing).toHaveCount(0);
  await expect(page.getByRole('dialog', { name: 'New event' })).toBeVisible();
  await expect(page.getByLabel('Description')).toHaveValue('The committee reviews the agenda.');
  // Nothing of the list or its dialog stays over the form, nor once the form has gone.
  await editor.getByLabel('Title').click();
  await editor.getByLabel('Title').fill('Committee');
  await expect(editor.getByLabel('Title')).toHaveValue('Committee');
  await editor.getByRole('button', { name: 'Cancel' }).click();
  await expect(editor).toHaveCount(0);
  await page.getByRole('button', { name: 'New event' }).first().click();
  await expect(page.getByRole('dialog', { name: 'New event' })).toBeVisible();
});

test('a guest is suggested from the contacts, as a message recipient is', async ({
  page,
  authenticate,
  mockApi,
}) => {
  await page.setViewportSize({ width: 1280, height: 900 });
  await authenticate({ timezone: 'Europe/Paris' });
  const asked: string[] = [];
  await playTheApi(mockApi, [
    {
      url: '**/api/v1/workbench/mail/recipients*',
      method: 'GET',
      handler: async route => {
        const query = new URL(route.request().url()).searchParams.get('q') ?? '';
        asked.push(query);
        const marc = query.toLowerCase().startsWith('mar');
        await route.fulfill({
          json: {
            query,
            suggestions: marc ? [{ name: 'Marc Dupont', email: 'marc@example.org' }] : [],
            truncated: false,
          },
        });
      },
    },
  ]);

  await page.goto(`/en/dashboard/tools/calendar?view=week&day=${TODAY}`);
  await waitForHydration(page, 'button');
  await page.getByRole('button', { name: 'New event' }).first().click();
  const guests = page.getByRole('combobox', { name: 'Guests' });
  await guests.fill('Mar');

  await expect(page.getByRole('option', { name: /Marc Dupont/ })).toBeVisible();
  await page.keyboard.press('ArrowDown');
  await page.keyboard.press('Enter');

  await expect(guests).toHaveValue('marc@example.org, ');
  expect(asked).toContain('Mar');
});

test('the keyboard opens an event and gets its link back when it closes', async ({
  page,
  authenticate,
  mockApi,
}) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await authenticate({ timezone: 'Europe/Paris' });
  await playTheApi(mockApi);

  await page.goto(`/en/dashboard/tools/calendar?view=agenda&day=${TODAY}`);
  await waitForHydration(page, 'button');
  const link = page.getByRole('link', { name: /Committee review/ });
  await link.focus();
  await page.keyboard.press('Enter');

  const close = page.getByRole('button', { name: 'Calendar' });
  await expect(close).toBeFocused();
  await expectNoOverflow(page, 'event at 390px');
  await page.keyboard.press('Enter');

  await expect(page.getByRole('link', { name: /Committee review/ })).toBeFocused();
});

/* PHONE LINES: the owner's remarks of 2026-11-06. */
for (const width of [390, 360, 320]) {
  test(`a phone reads the calendar line by line at ${width}px`, async ({
    page,
    authenticate,
    mockApi,
  }, testInfo) => {
    await page.setViewportSize({ width, height: 844 });
    await authenticate({ timezone: 'Europe/Paris' });
    await playTheApi(mockApi);

    await page.goto(`/en/dashboard/tools/calendar?view=agenda&day=${TODAY}`);
    await waitForHydration(page, 'button');
    await expect(page.getByText('Weekly sync').first()).toBeVisible();
    const tool = page.getByRole('region', { name: 'Calendar' });
    const search = page.getByRole('button', { name: 'Search across your tools' });
    const refresh = page.getByRole('button', { name: 'Refresh' });
    const event = page.getByRole('button', { name: 'New event' }).first();
    await expectOnOneLine(search, refresh, event);
    await expectSameStart(search, tool);
    await expectSameEnd(event, tool);
    await expect(tool.getByText(/Europe\/Paris/)).toHaveCount(0);
    // Today starts the line, what is shown ends it, and the search takes all the room it can.
    const today = tool.getByRole('button', { name: 'Today' });
    const shown = tool.getByRole('heading', { level: 2 });
    const searching = tool.getByRole('search');
    const calendars = tool.getByRole('button', { name: 'Calendars' });
    await expectSameStart(today, searching);
    await expectSameEnd(shown, calendars);
    await expectOnOneLine(searching, calendars);
    const box = await boxOf(tool.getByRole('searchbox'));
    const field = await boxOf(searching);
    expect(box.x, 'the field starts the search').toBeLessThanOrEqual(field.x + 1);
    expect((await boxOf(calendars)).x - (field.x + field.width)).toBeLessThanOrEqual(9);
    await expectLinesCentredIn(tool, tool.getByRole('group', { name: 'View' }));

    await page.getByRole('link').filter({ hasText: 'Weekly sync' }).first().click();
    const detail = page.getByRole('article', { name: 'Weekly sync' });
    const edit = detail.getByRole('button', { name: 'Edit', exact: true });
    const series = detail.getByRole('button', { name: 'Edit the series' });
    const copy = detail.getByRole('button', { name: 'Duplicate' });
    const remove = detail.getByRole('button', { name: 'Delete' });
    const ask = detail.getByRole('button', { name: 'Ask LIA' });
    await expectOnOneLine(
      detail.getByRole('button', { name: 'Calendar' }),
      edit,
      series,
      copy,
      remove,
      ask
    );
    await expectUnder(ask, detail.getByRole('heading', { level: 2 }));
    await expectInside(detail, ask);
    await expect(detail.getByRole('button', { name: 'More actions' })).toHaveCount(0);
    await expectNoOverflow(page, `the event's acts at ${width}px`);

    // The longer French label must keep the same header row on the smallest phone.
    await page.goto(`/fr/dashboard/tools/calendar?view=agenda&day=${TODAY}`);
    await waitForHydration(page, 'button');
    const frenchTool = page.getByRole('region', { name: 'Agenda', exact: true });
    const frenchSearch = page.getByRole('button', { name: 'Chercher dans tes outils' });
    const frenchRefresh = page.getByRole('button', { name: 'Actualiser', exact: true });
    const frenchEvent = page.getByRole('button', { name: 'Nouvel événement' }).first();
    await expect(frenchEvent).toBeVisible();
    await expectOnOneLine(frenchSearch, frenchRefresh, frenchEvent);
    await expectSameStart(frenchSearch, frenchTool);
    await expectSameEnd(frenchEvent, frenchTool);
    await expectNoOverflow(page, `French calendar actions at ${width}px`);
    await page.screenshot({ path: testInfo.outputPath(`calendar-actions-fr-${width}.png`) });
    await frenchEvent.click();
    await expect(page.getByRole('dialog', { name: 'Nouvel événement' })).toBeVisible();
  });
}

test('beside the view an open event keeps its acts in the same bar', async ({
  page,
  authenticate,
  mockApi,
}) => {
  await page.setViewportSize({ width: 1440, height: 900 });
  await authenticate({ timezone: 'Europe/Paris' });
  await playTheApi(mockApi);

  await page.goto(`/en/dashboard/tools/calendar?view=agenda&day=${TODAY}`);
  await waitForHydration(page, 'button');
  await page.getByRole('link').filter({ hasText: 'Weekly sync' }).first().click();
  const detail = page.getByRole('article', { name: 'Weekly sync' });

  await expectOnOneLine(
    detail.getByRole('button', { name: 'Close the event' }),
    detail.getByRole('button', { name: 'Edit', exact: true }),
    detail.getByRole('button', { name: 'Edit the series' }),
    detail.getByRole('button', { name: 'Duplicate' }),
    detail.getByRole('button', { name: 'Delete' }),
    detail.getByRole('button', { name: 'Ask LIA' })
  );

  // The acts close the bar, however wide the pane.
  const bar = await boxOf(detail.getByTestId('detail-bar'));
  const ask = await boxOf(detail.getByRole('button', { name: 'Ask LIA' }));
  expect(bar.x + bar.width - (ask.x + ask.width)).toBeLessThan(12);
});
