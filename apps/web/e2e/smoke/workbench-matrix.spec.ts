/**
 * The six « Tools » screens across the matrix, hermetic (ADR-369, Task 10.1).
 *
 * The API is played by one switch: every tool ready, a little data each. Each
 * screen is proven at 320 px (the phone), at 200 % zoom (1280 px read as 640
 * CSS pixels) and in the five accents: no horizontal scroll, axe clean on the
 * screen; on the phone the row of tools scrolls itself to the open one, and
 * the section opens on its first tool. On a computer each screen runs the whole
 * window while the other pages keep their rail. With `E2E_SHOT_DIR` set, each
 * accent's screen and each screen at 1920 px are kept as evidence.
 * Run with `E2E_ALL_BROWSERS=1` for the Firefox and WebKit smoke.
 */
import AxeBuilder from '@axe-core/playwright';
import type { Locator, Page, Route } from '@playwright/test';

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

const READY: Record<string, { provider: string; features: string[] }> = {
  mail: { provider: 'google_gmail', features: ['mark_read', 'drafts', 'labels'] },
  calendar: { provider: 'google_calendar', features: ['all_day', 'occurrence_edit'] },
  tasks: { provider: 'google_tasks', features: ['due_date_only', 'list_management'] },
  contacts: { provider: 'google_contacts', features: ['multi_valued', 'contact_groups'] },
  files: { provider: 'google_drive', features: ['export'] },
  lights: { provider: 'philips_hue', features: ['scenes'] },
};

const RAIL = {
  tools: Object.entries(READY).map(([tool, ready]) => ({
    tool,
    state: 'ready',
    ...ready,
    bounds: { values_max: 20, value_max_chars: 320, title_max_chars: 1024 },
  })),
  limits: {
    page_size: 25,
    bulk_max_items: 50,
    download_max_bytes: 26214400,
    calendar_window_max_events: 500,
  },
};

/** What each screen shows once its data is in, to wait on. */
const SCREENS = [
  { tool: 'mail', shows: 'Committee agenda for Thursday' },
  { tool: 'calendar', shows: 'Committee review' },
  { tool: 'tasks', shows: 'Call the plumber' },
  { tool: 'contacts', shows: 'Ana Lima' },
  { tool: 'files', shows: 'Projects 2026' },
  { tool: 'lights', shows: 'Living room' },
] as const;

const ANSWERS: Array<[RegExp, unknown]> = [
  [
    /\/mail\/folders$/,
    {
      folders: [
        { id: 'system:inbox', kind: 'system', role: 'inbox', name: null },
        { id: 'system:trash', kind: 'system', role: 'trash', name: null },
      ],
    },
  ],
  [
    /\/mail\/messages$/,
    {
      items: [
        {
          id: 'm1',
          thread_id: 'm1',
          sender: { name: 'Camille Martin', address: 'camille@example.org' },
          subject: 'Committee agenda for Thursday',
          snippet: 'Hello everyone, here is the proposed agenda…',
          received_at: new Date().toISOString(),
          is_read: false,
          is_starred: false,
          label_ids: [],
        },
      ],
      next_page_token: null,
      skipped: 0,
    },
  ],
  [
    /\/calendar\/calendars$/,
    {
      calendars: [
        { id: 'primary', name: 'Ana Lima', color: '#7c3aed', primary: true, writable: true },
      ],
    },
  ],
  [
    /\/calendar\/events$/,
    {
      calendars: [
        {
          calendar_id: 'primary',
          events: [
            {
              id: 'e1',
              calendar_id: 'primary',
              summary: 'Committee review',
              all_day: false,
              start: `${TODAY}T11:00:00Z`,
              end: `${TODAY}T12:00:00Z`,
              location: null,
              recurring: false,
              conference_url: null,
            },
          ],
          truncated: false,
          skipped: 0,
          error: null,
        },
      ],
    },
  ],
  [/\/tasks\/lists$/, { items: [{ id: 'l1', title: 'My tasks' }], next_page_token: null }],
  [
    /\/tasks$/,
    {
      items: [
        {
          id: 't1',
          title: 'Call the plumber',
          notes: null,
          completed: false,
          due: TODAY,
          parent: null,
          position: '1',
        },
      ],
      next_page_token: null,
    },
  ],
  [/\/contacts\/groups$/, { groups: [] }],
  [
    /\/contacts$/,
    {
      items: [
        {
          id: 'people/c1',
          name: 'Ana Lima',
          email: 'ana@example.org',
          phone: null,
          organization: 'Atlas',
          name_key: 'ana lima',
        },
      ],
      next_page_token: null,
      truncated: false,
    },
  ],
  [
    /\/files$/,
    {
      items: [
        {
          id: 'd1',
          name: 'Projects 2026',
          kind: 'folder',
          mime_type: 'application/vnd.google-apps.folder',
          modified_at: new Date().toISOString(),
          size: null,
          web_url: null,
          target_id: null,
          target_kind: null,
          formats: [],
          downloadable: false,
        },
      ],
      next_page_token: null,
    },
  ],
  [
    /\/lights$/,
    {
      rooms: [{ id: 'r1', name: 'Living room', light_ids: ['a'], on: true }],
      lights: [
        {
          id: 'a',
          name: 'Floor lamp',
          room_id: 'r1',
          on: true,
          brightness: 70,
          supports_color: false,
          color_hex: null,
          mirek: null,
          mirek_min: null,
          mirek_max: null,
        },
      ],
      scenes: [],
    },
  ],
];

async function answer(route: Route): Promise<void> {
  const path = new URL(route.request().url()).pathname;
  const found = ANSWERS.find(([pattern]) => pattern.test(path));
  await route.fulfill({ json: found ? found[1] : {} });
}

async function playTheWorkbench(mockApi: (routes: MockRoute[]) => Promise<void>) {
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
    { url: '**/api/v1/workbench/**', method: 'GET', handler: answer },
  ]);
}

async function openScreen(page: Page, tool: string, shows: string): Promise<void> {
  await page.goto(`/en/dashboard/tools/${tool}`);
  await waitForHydration(page, 'main');
  await expect(page.getByText(shows).first()).toBeVisible();
}

async function expectAxeClean(page: Page): Promise<void> {
  const scan = await new AxeBuilder({ page }).include('main').analyze();
  expect(scan.violations).toEqual([]);
}

/** What a tool works in: whatever follows its heading row, panes or cards. */
function toolArea(page: Page): Locator {
  return page.locator('main div:has(> h1) + *');
}

/** Where a box starts and ends across the window, in whole pixels. */
async function span(box: Locator): Promise<{ left: number; right: number }> {
  const drawn = await box.boundingBox();
  if (!drawn) throw new Error('the box is not drawn');
  return { left: Math.round(drawn.x), right: Math.round(drawn.x + drawn.width) };
}

for (const screen of SCREENS) {
  test(`${screen.tool} at 320 px and at 200 % zoom`, async ({ page, authenticate, mockApi }) => {
    await authenticate({ timezone: 'Europe/Paris' });
    await playTheWorkbench(mockApi);

    await page.setViewportSize({ width: 320, height: 640 });
    await openScreen(page, screen.tool, screen.shows);
    await expectNoOverflow(page, `${screen.tool} 320px`);
    await expectAxeClean(page);
    // The row scrolls inside itself: the open tool's pill is whole on screen.
    const rail = page.getByRole('navigation', { name: 'Your tools' });
    await expect(rail.locator('a[aria-current="page"]')).toBeInViewport({ ratio: 1 });

    // 1280 px at 200 %: the layout a 640-pixel viewport gets.
    await page.setViewportSize({ width: 640, height: 450 });
    await openScreen(page, screen.tool, screen.shows);
    await expectNoOverflow(page, `${screen.tool} 200%`);
  });
}

test('the section opens its first ready tool on a phone', async ({
  page,
  authenticate,
  mockApi,
}) => {
  await authenticate({ timezone: 'Europe/Paris' });
  await playTheWorkbench(mockApi);
  await page.setViewportSize({ width: 320, height: 640 });

  await page.goto('/en/dashboard/tools');

  await expect(page).toHaveURL(/\/dashboard\/tools\/mail$/);
  await expect(page.getByRole('heading', { level: 1, name: 'Mail' })).toBeVisible();
  await expectNoOverflow(page, 'tools root 320px');
});

test('a pane sized by hand keeps its width on this device, and a double-click gives it back', async ({
  page,
  authenticate,
  mockApi,
}) => {
  await authenticate({ timezone: 'Europe/Paris' });
  await playTheWorkbench(mockApi);
  await page.setViewportSize({ width: 1440, height: 900 });
  await openScreen(page, 'contacts', 'Ana Lima');
  const separator = page.getByRole('separator', { name: 'Resize the contact list' });
  // Read through the separator EVERY time: the pane's id comes from `useId`, and
  // a reload renders the tree afresh — the id read before it named another
  // element afterwards (measured: a 1 px box).
  const width = async () => {
    const pane = page.locator(`[id="${await separator.getAttribute('aria-controls')}"]`);
    return Math.round((await pane.boundingBox())?.width ?? 0);
  };
  const drawn = await width();

  const handle = await separator.boundingBox();
  if (!handle) throw new Error('the separator is not drawn');
  const y = handle.y + handle.height / 2;
  await page.mouse.move(handle.x + handle.width / 2, y);
  await page.mouse.down();
  await page.mouse.move(handle.x + handle.width / 2 + 120, y, { steps: 6 });
  await page.mouse.up();
  await expect.poll(width).toBe(drawn + 120);
  await expectNoOverflow(page, 'contacts list sized');

  await page.reload();
  await waitForHydration(page, 'main');
  await expect(page.getByText('Ana Lima').first()).toBeVisible();
  await expect.poll(width).toBe(drawn + 120);

  await separator.dblclick();
  await expect.poll(width).toBe(drawn);
});

/**
 * Owner request (2026-11-04): on a computer the tools use the whole window, less
 * a 16 px gutter — on any screen they had the rail's 1216 px — and every other
 * page keeps the rail, 1280 px in the middle of a 1920 px window.
 */
test('on a computer each tool runs the whole window, and another page keeps its rail', async ({
  page,
  authenticate,
  mockApi,
}) => {
  test.setTimeout(180_000);
  await page.setViewportSize({ width: 1920, height: 1080 });
  await authenticate({ timezone: 'Europe/Paris' });
  await playTheWorkbench(mockApi);

  for (const screen of SCREENS) {
    await openScreen(page, screen.tool, screen.shows);
    await expect
      .poll(() => span(toolArea(page)), { message: screen.tool })
      .toEqual({ left: 16, right: 1904 });
    await expectNoOverflow(page, `${screen.tool} 1920px`);
    const dir = process.env.E2E_SHOT_DIR;
    if (dir) await page.screenshot({ path: `${dir}/wide_${screen.tool}.png` });
  }

  await page.goto('/en/dashboard/faq');
  await waitForHydration(page, 'main');
  await expect.poll(() => span(page.locator('main'))).toEqual({ left: 320, right: 1600 });
});

test('a tool leaves the frame of the other pages where a computer starts, not before', async ({
  page,
  authenticate,
  mockApi,
}) => {
  await authenticate({ timezone: 'Europe/Paris' });
  await playTheWorkbench(mockApi);

  await page.setViewportSize({ width: 1023, height: 800 });
  await openScreen(page, 'contacts', 'Ana Lima');
  await expect.poll(() => span(toolArea(page))).toEqual({ left: 24, right: 999 });

  await page.setViewportSize({ width: 1024, height: 800 });
  await expect.poll(() => span(toolArea(page))).toEqual({ left: 16, right: 1008 });
});

test('the whole window holds in the default language, whose addresses carry no prefix', async ({
  page,
  authenticate,
  mockApi,
}) => {
  await page.setViewportSize({ width: 1920, height: 1080 });
  await authenticate({ timezone: 'Europe/Paris', language: 'fr' });
  await playTheWorkbench(mockApi);

  await page.goto('/fr/dashboard/tools/mail');
  await waitForHydration(page, 'main');
  await expect(page.getByText('Committee agenda for Thursday').first()).toBeVisible();

  expect(new URL(page.url()).pathname).toBe('/dashboard/tools/mail');
  await expect.poll(() => span(toolArea(page))).toEqual({ left: 16, right: 1904 });
});

test('the notice of a broken connector stands as wide as the page under it', async ({
  page,
  authenticate,
  mockApi,
}) => {
  await page.setViewportSize({ width: 1920, height: 1080 });
  await authenticate({ timezone: 'Europe/Paris' });
  await playTheWorkbench(mockApi);
  await mockApi([
    {
      url: '**/api/v1/connectors/health',
      json: {
        connectors: [
          {
            id: 'conn-google-gmail',
            connector_type: 'google_gmail',
            display_name: 'Gmail',
            health_status: 'error',
            severity: 'critical',
            expires_in_minutes: null,
            authorize_url: '/connectors/google_gmail/authorize',
          },
        ],
        has_issues: true,
        critical_count: 1,
        warning_count: 0,
        checked_at: '2026-11-04T10:00:00Z',
      },
    },
  ]);
  const notice = page.getByRole('status', { name: 'Connector status' }).locator('> div');

  await openScreen(page, 'mail', 'Committee agenda for Thursday');
  await page.getByRole('button', { name: 'Later' }).click();
  await expect(notice).toBeVisible();
  await expect.poll(() => span(notice)).toEqual({ left: 16, right: 1904 });
  await expect.poll(() => span(toolArea(page))).toEqual({ left: 16, right: 1904 });

  await page.goto('/en/dashboard/faq');
  await waitForHydration(page, 'main');
  await expect(notice).toBeVisible();
  await expect.poll(() => span(notice)).toEqual({ left: 352, right: 1568 });
});

for (const accent of ['default', 'ocean', 'forest', 'sunset', 'slate'] as const) {
  test(`every screen in the ${accent} accent`, async ({ page, authenticate, mockApi }) => {
    test.setTimeout(180_000);
    await page.setViewportSize({ width: 1280, height: 900 });
    await prepareTheme(page, accent === 'slate' ? 'dark' : 'light');
    await page.addInitScript(chosen => localStorage.setItem('color-theme', chosen), accent);
    await authenticate({ timezone: 'Europe/Paris' });
    await playTheWorkbench(mockApi);

    for (const screen of SCREENS) {
      await openScreen(page, screen.tool, screen.shows);
      await expectAxeClean(page);
      const dir = process.env.E2E_SHOT_DIR;
      if (dir) await page.screenshot({ path: `${dir}/l10_${accent}_${screen.tool}.png` });
    }
  });
}
