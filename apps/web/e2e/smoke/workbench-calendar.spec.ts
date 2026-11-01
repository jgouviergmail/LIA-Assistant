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
import type { Route } from '@playwright/test';

import { test, expect, waitForHydration } from '../fixtures';
import type { MockRoute } from '../fixtures/api-mock';
import { appConfig } from '../fixtures/dashboard-shell';
import { expectNoOverflow, prepareTheme } from './overflow-report';

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
          features: ['all_day', 'conference', 'notify_attendees', 'occurrence_edit'],
          bounds: {
            summary_max_chars: 1024,
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
    calendar_window_max_events: 500,
  },
};

const CALENDARS = [
  { id: 'primary', name: 'Ana Lima', color: '#7c3aed', primary: true, writable: true },
  { id: 'team', name: 'Team', color: '#059669', primary: false, writable: true },
];

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
  await route.fulfill({
    json: { ...event, description: null, attendees: [], organizer: null, link: null },
  });
}

async function playTheApi(
  mockApi: (routes: MockRoute[]) => Promise<void>,
  extra: MockRoute[] = []
) {
  await mockApi([
    {
      url: '**/api/v1/config',
      json: {
        ...appConfig,
        features: { ...appConfig.features, workbench_enabled: true },
        capabilities: { workbench: { enabled: true, family: 'work' } },
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
  await page.getByRole('link', { name: /Weekly sync/ }).click();

  const detail = page.getByRole('article', { name: 'Weekly sync' });
  await expect(detail.getByText(/reaches this occurrence only/)).toBeVisible();
  await expect(detail.getByRole('link', { name: 'Join the video call' })).toHaveAttribute(
    'rel',
    /noopener/
  );
});

/**
 * Owner request (2026-10-31): a guest is suggested from the account's contacts exactly as a
 * message's recipient is — the same field, the same door, picked with the keyboard.
 */
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

  const close = page.getByRole('button', { name: 'Close the event' });
  await expect(close).toBeFocused();
  await expectNoOverflow(page, 'event at 390px');
  await page.keyboard.press('Enter');

  await expect(page.getByRole('link', { name: /Committee review/ })).toBeFocused();
});
