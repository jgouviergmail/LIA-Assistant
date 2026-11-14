/**
 * The « Tools » tasks screen, hermetic (ADR-369, Task 6.2).
 *
 * The API is played by the spec: one ready tasks provider, two lists, a page
 * that says more exists, a subtask, a due day today and one overdue. Proven at
 * 1280 and 390 px, in light, dark and OLED: no horizontal scroll, axe clean on
 * the screen; a refused completion is rolled back and said in the refusal's
 * own words; the keyboard opens a task and gets its row back when it closes.
 * Every list together (2026-11-10): « All tasks » heads the lists and names each
 * task's list in a badge, a task opens BESIDE it and closing comes back to it;
 * « All » cuts what is late, today's and the days ahead into titled stretches.
 * With nothing named in the address the screen opens on « All tasks » (owner, 2026-11-10):
 * the default list is where a new task goes, not where the screen starts.
 */
import AxeBuilder from '@axe-core/playwright';

import { test, expect, waitForHydration } from '../fixtures';
import type { MockRoute } from '../fixtures/api-mock';
import { appConfig } from '../fixtures/dashboard-shell';
import { expectNoOverflow, prepareTheme } from './overflow-report';
import {
  expectInside,
  expectLinesCentredIn,
  expectNoZoomOnFocus,
  expectOnOneLine,
  expectSameStart,
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

/** A list on screen: the address names it, since a bare one opens on « All tasks ». */
const A_LIST = '/en/dashboard/tools/tasks?list=l1';

const RAIL = {
  tools: ['mail', 'calendar', 'tasks', 'contacts', 'files', 'lights'].map(tool =>
    tool === 'tasks'
      ? {
          tool,
          state: 'ready',
          provider: 'google_tasks',
          features: ['due_date_only', 'list_management', 'subtasks'],
          bounds: { title_max_chars: 1024, notes_max_chars: 8192 },
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

const TASKS = [
  {
    id: 't1',
    title: 'Send back the insurance form',
    notes: null,
    completed: false,
    due: TODAY,
    parent: null,
    position: '1',
    steps: [],
    importance: null,
    reminder: null,
    repeat: null,
  },
  {
    id: 't2',
    title: 'Prepare the committee deck',
    notes: 'Ten slides at most.',
    completed: false,
    due: shifted(4),
    parent: null,
    position: '2',
    steps: [],
    importance: null,
    reminder: null,
    repeat: null,
  },
  {
    id: 't2a',
    title: 'Gather the quarter figures',
    notes: null,
    completed: false,
    due: null,
    parent: 't2',
    position: '1',
    steps: [],
    importance: null,
    reminder: null,
    repeat: null,
  },
  {
    id: 't3',
    title: 'Call the plumber',
    notes: null,
    completed: false,
    due: shifted(-2),
    parent: null,
    position: '3',
    steps: [],
    importance: null,
    reminder: null,
    repeat: null,
  },
];

const VIEW = {
  tasks: [{ id: 't1', list_id: 'l2', title: 'Send back the insurance form', due: TODAY }],
  truncated: false,
  failed: [],
};

/** A list whose name no row of a phone holds whole. */
const LONG_LIST = 'Household paperwork and everything the family keeps putting off until later';

/** What is late, today's and the days ahead, as the server orders them. */
const TIMELINE = [
  { id: 't3', list_id: 'l1', title: 'Call the plumber', due: shifted(-2) },
  { id: 't1', list_id: 'l2', title: 'Send back the insurance form', due: TODAY },
  { id: 't2', list_id: 'l1', title: 'Prepare the committee deck', due: shifted(4) },
];

/** What each view across the lists answers; the days' own views keep `VIEW`. */
const VIEWS: Record<string, { tasks: object[]; truncated: boolean; failed: string[] }> = {
  timeline: { tasks: TIMELINE, truncated: false, failed: [] },
  all: {
    tasks: [
      ...TIMELINE,
      { id: 't4', list_id: 'l3', title: 'Renew the passport', due: shifted(40) },
      { id: 't2a', list_id: 'l1', title: 'Gather the quarter figures', due: null },
    ],
    truncated: false,
    failed: [],
  },
};

async function playTheApi(mockApi: (routes: MockRoute[]) => Promise<void>, refuse = false) {
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
    {
      url: '**/api/v1/workbench/tasks/lists*',
      json: {
        items: [
          { id: 'l1', title: 'My tasks' },
          { id: 'l2', title: 'Groceries' },
          { id: 'l3', title: LONG_LIST },
        ],
        next_page_token: null,
      },
    },
    {
      url: '**/api/v1/workbench/tasks/view*',
      method: 'GET',
      handler: async route => {
        const view = new URL(route.request().url()).searchParams.get('view') ?? '';
        await route.fulfill({ json: VIEWS[view] ?? VIEW });
      },
    },
    {
      url: '**/api/v1/workbench/tasks/selection/move',
      method: 'POST',
      handler: async route => {
        const { task_ids: ids } = route.request().postDataJSON() as { task_ids: string[] };
        await route.fulfill({
          json: { done: ids, failed: [], moved: ids.map(id => ({ id, new_id: `${id}-copy` })) },
        });
      },
    },
    {
      // A task a view names that its list's page does not hold is read alone.
      url: '**/api/v1/workbench/tasks/task*',
      method: 'GET',
      json: { ...TASKS[0], id: 't4', title: 'Renew the passport', due: shifted(40) },
    },
    {
      url: '**/api/v1/workbench/tasks*',
      method: 'GET',
      json: { items: TASKS, next_page_token: 'p2' },
    },
    {
      url: '**/api/v1/workbench/tasks',
      method: 'PATCH',
      handler: async route => {
        if (refuse) {
          await route.fulfill({ status: 502, json: { detail: { code: 'provider_unavailable' } } });
          return;
        }
        const change = route.request().postDataJSON() as { task_id: string; completed?: boolean };
        const task = TASKS.find(item => item.id === change.task_id);
        await route.fulfill({ json: { ...task, ...change } });
      },
    },
  ]);
}

for (const sample of [
  { width: 1280, theme: 'light' },
  { width: 1280, theme: 'dark' },
  { width: 390, theme: 'oled' },
] as const) {
  test(`tasks screen at ${sample.width}px in ${sample.theme}`, async ({
    page,
    authenticate,
    mockApi,
  }) => {
    await page.setViewportSize({ width: sample.width, height: 900 });
    await prepareTheme(page, sample.theme);
    await authenticate({ timezone: 'Europe/Paris' });
    await playTheApi(mockApi);

    await page.goto(A_LIST);
    await waitForHydration(page, 'input[type="checkbox"]');
    await expect(page.getByText('Call the plumber')).toBeVisible();
    await expect(page.getByRole('button', { name: 'Load more' })).toBeVisible();

    await expectNoOverflow(page, `${sample.width}px ${sample.theme}`);
    const scan = await new AxeBuilder({ page }).include('main').analyze();
    expect(scan.violations).toEqual([]);
  });
}

test('with nothing named, the screen opens on « all tasks »', async ({
  page,
  authenticate,
  mockApi,
}) => {
  await page.setViewportSize({ width: 1280, height: 900 });
  await authenticate({ timezone: 'Europe/Paris' });
  await playTheApi(mockApi);

  await page.goto('/en/dashboard/tools/tasks');
  await waitForHydration(page, 'input[type="checkbox"]');

  // Every list's tasks stand there, each naming its list; the address is left as it came.
  await expect(page.getByRole('heading', { name: 'All tasks' })).toBeVisible();
  const rows = page.getByRole('region', { name: 'Tasks', exact: true }).getByRole('listitem');
  await expect(rows).toHaveCount(5);
  await expect(page.getByRole('link', { name: /Renew the passport/ })).toBeVisible();
  await expect(page).toHaveURL(/\/tools\/tasks$/);
  const lists = page.getByRole('navigation', { name: 'Lists' });
  await expect(lists.getByRole('link', { name: 'All tasks' })).toHaveAttribute(
    'aria-current',
    'page'
  );
  await expect(lists.getByRole('link', { name: 'My tasks' })).not.toHaveAttribute('aria-current');

  // A list is one click away, and « back » to every list is too.
  await lists.getByRole('link', { name: 'My tasks' }).click();
  await expect(page).toHaveURL(/list=l1$/);
  await expect(page.getByRole('button', { name: 'Load more' })).toBeVisible();
  await expectNoOverflow(page, 'the opening at 1280px');
  expect((await new AxeBuilder({ page }).include('main').analyze()).violations).toEqual([]);
});

test('on a phone too, the screen opens on « all tasks » and says so in its select', async ({
  page,
  authenticate,
  mockApi,
}) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await prepareTheme(page, 'oled');
  await authenticate({ timezone: 'Europe/Paris' });
  await playTheApi(mockApi);

  await page.goto('/en/dashboard/tools/tasks');
  await waitForHydration(page, 'input[type="checkbox"]');

  await expect(page.getByRole('heading', { name: 'All tasks' })).toBeVisible();
  await expect(
    page.getByRole('combobox', { name: 'List', exact: true }).locator('option:checked')
  ).toHaveText('All tasks');
  await expect(page.getByRole('link', { name: /Send back the insurance form/ })).toContainText(
    'Groceries'
  );
  await expectNoOverflow(page, 'the opening at 390px');
  expect((await new AxeBuilder({ page }).include('main').analyze()).violations).toEqual([]);
});

test("a view gathers the lists, names each task's list and stays within a phone", async ({
  page,
  authenticate,
  mockApi,
}) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await authenticate({ timezone: 'Europe/Paris' });
  await playTheApi(mockApi);

  await page.goto('/en/dashboard/tools/tasks');
  await waitForHydration(page, 'input[type="checkbox"]');
  await page.getByRole('combobox', { name: 'List', exact: true }).selectOption({ label: 'Today' });
  await expect(page).toHaveURL(/view=today/);

  await expect(page.getByRole('heading', { name: 'Today' })).toBeVisible();
  await expect(page.getByRole('link', { name: /Send back the insurance form/ })).toContainText(
    'Groceries'
  );
  await expectNoOverflow(page, 'a view at 390px');
  const scan = await new AxeBuilder({ page }).include('main').analyze();
  expect(scan.violations).toEqual([]);
});

for (const theme of ['light', 'dark', 'oled'] as const) {
  test(`« all tasks » names each task's list in ${theme}, and a task opens beside it`, async ({
    page,
    authenticate,
    mockApi,
  }) => {
    await page.setViewportSize({ width: 1280, height: 900 });
    await prepareTheme(page, theme);
    await authenticate({ timezone: 'Europe/Paris' });
    await playTheApi(mockApi);

    await page.goto('/en/dashboard/tools/tasks');
    await waitForHydration(page, 'input[type="checkbox"]');
    const lists = page.getByRole('navigation', { name: 'Lists' });
    // It heads the lists, the three days together head the views.
    await expect(lists.getByRole('link').first()).toHaveText('All');
    await lists.getByRole('link', { name: 'All tasks' }).click();
    await expect(page).toHaveURL(/view=all$/);
    await expect(page.getByRole('heading', { name: 'All tasks' })).toBeVisible();

    // Every list's tasks, the undated last, each naming its list.
    const rows = page.getByRole('region', { name: 'Tasks', exact: true }).getByRole('listitem');
    await expect(rows).toHaveCount(5);
    await expect(rows.first()).toContainText('Call the plumber');
    const undated = page.getByRole('link', { name: /Gather the quarter figures/ });
    await expect(rows.last()).toContainText('Gather the quarter figures');
    await expect(undated).toContainText('My tasks');
    await expect(page.getByRole('link', { name: /Send back the insurance form/ })).toContainText(
      'Groceries'
    );
    await expectNoOverflow(page, `all tasks in ${theme}`);
    expect((await new AxeBuilder({ page }).include('main').analyze()).violations).toEqual([]);

    // A task opens BESIDE the view, which stays on screen.
    await page.getByRole('link', { name: /Prepare the committee deck/ }).click();
    await expect(page).toHaveURL(/view=all&list=l1&task=t2$/);
    const detail = page.getByRole('complementary', { name: 'Detail' });
    await expect(detail.getByRole('textbox', { name: 'Title' })).toHaveValue(
      'Prepare the committee deck'
    );
    await expect(page.getByRole('heading', { name: 'All tasks' })).toBeVisible();
    await expect(undated).toBeVisible();
    await expect(page.getByRole('link', { name: /Prepare the committee deck/ })).toHaveAttribute(
      'aria-current',
      'true'
    );
    await expectNoOverflow(page, `a task beside all tasks in ${theme}`);
    expect((await new AxeBuilder({ page }).include('main').analyze()).violations).toEqual([]);

    // A late task opens from the view the same way: its warning chip stays readable on the
    // open row, whose own tint the list's badge does not add to.
    await page.getByRole('link', { name: /Call the plumber/ }).click();
    await expect(page).toHaveURL(/view=all&list=l1&task=t3$/);
    await expect(detail.getByRole('textbox', { name: 'Title' })).toHaveValue('Call the plumber');
    expect((await new AxeBuilder({ page }).include('main').analyze()).violations).toEqual([]);

    // Closing comes back to the view, and to the row that opened the task.
    await detail.getByRole('button', { name: 'Close the detail' }).click();
    await expect(page).toHaveURL(/view=all$/);
    await expect(page.getByRole('heading', { name: 'All tasks' })).toBeVisible();
    await expect(page.getByRole('link', { name: /Call the plumber/ })).toBeFocused();
  });
}

for (const theme of ['light', 'dark'] as const) {
  test(`« all » cuts what is late, today and ahead into titled stretches, on a phone in ${theme}`, async ({
    page,
    authenticate,
    mockApi,
  }) => {
    await page.setViewportSize({ width: 390, height: 844 });
    await prepareTheme(page, theme);
    await authenticate({ timezone: 'Europe/Paris' });
    await playTheApi(mockApi);

    await page.goto('/en/dashboard/tools/tasks');
    await waitForHydration(page, 'input[type="checkbox"]');
    await page.getByRole('combobox', { name: 'List', exact: true }).selectOption({ label: 'All' });
    await expect(page).toHaveURL(/view=timeline$/);

    await expect(page.getByRole('heading', { level: 3 })).toHaveText([
      /Overdue/,
      /Today/,
      /Coming up/,
    ]);
    const late = page.getByRole('region', { name: /Overdue/ });
    await expect(late.getByRole('link', { name: /Call the plumber/ })).toContainText('My tasks');
    await expect(late).toContainText('1 to do');
    await expect(page.getByRole('region', { name: /Today/ }).getByRole('link')).toHaveCount(1);
    await expect(page.getByRole('region', { name: /Coming up/ }).getByRole('link')).toHaveCount(1);
    await expectNoOverflow(page, `the timeline at 390px in ${theme}`);
    expect((await new AxeBuilder({ page }).include('main').analyze()).violations).toEqual([]);
  });
}

test('on a phone, « all tasks » keeps a long list name inside its row, and a task replaces it', async ({
  page,
  authenticate,
  mockApi,
}) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await prepareTheme(page, 'oled');
  await authenticate({ timezone: 'Europe/Paris' });
  await playTheApi(mockApi);

  await page.goto('/en/dashboard/tools/tasks');
  await waitForHydration(page, 'input[type="checkbox"]');
  await page
    .getByRole('combobox', { name: 'List', exact: true })
    .selectOption({ label: 'All tasks' });
  await expect(page).toHaveURL(/view=all$/);

  const row = page.getByRole('listitem').filter({ hasText: 'Renew the passport' });
  const badge = row.getByTitle(LONG_LIST);
  await expect(badge).toBeVisible();
  await expectInside(row, badge);
  await expectNoOverflow(page, 'all tasks at 390px');
  expect((await new AxeBuilder({ page }).include('main').analyze()).violations).toEqual([]);

  // Below lg the detail replaces the view; « back » returns to the view, not to a list.
  await row.getByRole('link', { name: /Renew the passport/ }).click();
  const detail = page.getByRole('complementary', { name: 'Detail' });
  await expect(detail.getByRole('textbox', { name: 'Title' })).toHaveValue('Renew the passport');
  await expectNoOverflow(page, 'a task of all tasks at 390px');
  await detail.getByRole('button', { name: 'Tasks' }).click();
  await expect(page).toHaveURL(/view=all$/);
  await expect(page.getByRole('heading', { name: 'All tasks' })).toBeVisible();
});

test('ticked tasks go to another list, and leave this one', async ({
  page,
  authenticate,
  mockApi,
}) => {
  await page.setViewportSize({ width: 1280, height: 900 });
  await authenticate({ timezone: 'Europe/Paris' });
  await playTheApi(mockApi);

  await page.goto(A_LIST);
  await waitForHydration(page, 'input[type="checkbox"]');
  await page.getByRole('button', { name: 'Select' }).click();
  await page.getByRole('checkbox', { name: 'Select: Send back the insurance form' }).check();

  const bar = page.getByRole('region', { name: 'Selected tasks' });
  await expect(bar).toBeVisible();
  const scan = await new AxeBuilder({ page }).include('main').analyze();
  expect(scan.violations).toEqual([]);

  // One line: the count and its way out, done as an icon, the rest behind « … », the deletion.
  const more = bar.getByRole('button', { name: 'More actions' });
  await expectOnOneLine(
    bar.getByText('1 selected'),
    bar.getByRole('button', { name: 'Clear the selection' }),
    bar.getByRole('button', { name: 'Mark done' }),
    more,
    bar.getByRole('button', { name: 'Delete' })
  );

  // Another list is a place: the lists stand under their own line. A hand crosses to them in
  // steps: from one jump a menu reads a pointer that left the other way, and closes its places.
  await more.click();
  await page.getByRole('menuitem', { name: 'Move to a list' }).click();
  const groceries = page.getByRole('menuitem', { name: 'Groceries' });
  const place = await groceries.boundingBox();
  if (place === null) throw new Error('the lists are not drawn');
  await page.mouse.move(place.x + place.width / 2, place.y + place.height / 2, { steps: 12 });
  await groceries.click();

  await expect(page.getByRole('link', { name: /Send back the insurance form/ })).toHaveCount(0);
  await expect(page.getByRole('link', { name: /Prepare the committee deck/ })).toBeVisible();
});

test('a long list scrolls inside its pane, never the page', async ({
  page,
  authenticate,
  mockApi,
}) => {
  await page.setViewportSize({ width: 1280, height: 700 });
  await authenticate({ timezone: 'Europe/Paris' });
  await playTheApi(mockApi);
  await mockApi([
    {
      url: '**/api/v1/workbench/tasks?*',
      handler: async route => {
        const many = Array.from({ length: 60 }, (_, index) => ({
          ...TASKS[0],
          id: `long-${index}`,
          title: `Task number ${index}`,
        }));
        await route.fulfill({ json: { items: many, next_page_token: null } });
      },
    },
  ]);

  await page.goto(A_LIST);
  await waitForHydration(page, 'input[type="checkbox"]');
  await expect(page.getByText('Task number 59')).toBeAttached();

  const frame = page.getByRole('region', { name: 'Tasks' });
  const box = await frame.boundingBox();
  expect(box!.y + box!.height).toBeLessThanOrEqual(700);
  const scroller = await page.evaluate(() => {
    const page = document.scrollingElement!;
    return page.scrollHeight <= page.clientHeight;
  });
  expect(scroller).toBe(true);
  await page.getByText('Task number 59').scrollIntoViewIfNeeded();
  await expect(page.getByText('Task number 59')).toBeInViewport();
});

test('a refused completion is rolled back and said in the refusal’s words', async ({
  page,
  authenticate,
  mockApi,
}) => {
  await page.setViewportSize({ width: 1280, height: 900 });
  await authenticate({ timezone: 'Europe/Paris' });
  await playTheApi(mockApi, true);

  await page.goto(A_LIST);
  await waitForHydration(page, 'input[type="checkbox"]');
  const box = page.getByRole('checkbox', { name: 'Mark as done: Call the plumber' });
  await box.click();

  await expect(page.getByText('The service is not answering: try again later.')).toBeVisible();
  await expect(box).not.toBeChecked();
});

test.describe('on a touch screen', () => {
  test.use({ hasTouch: true, isMobile: true, viewport: { width: 390, height: 844 } });
  test.skip(({ browserName }) => browserName === 'firefox', 'no mobile emulation');

  /** Owner report (2026-11-06): iOS zoomed into a small field and stayed there. */
  test('no field of the tasks is one iOS would zoom into', async ({
    page,
    authenticate,
    mockApi,
  }) => {
    await authenticate({ timezone: 'Europe/Paris' });
    await playTheApi(mockApi);
    await page.goto(A_LIST);
    await waitForHydration(page, 'main');
    await expect(page.getByText('Send back the insurance form').first()).toBeVisible();

    await expectNoZoomOnFocus(page);
    await page
      .getByRole('link', { name: /Send back the insurance form/ })
      .first()
      .click();
    await expect(page.getByLabel('Notes')).toBeVisible();
    await expectNoZoomOnFocus(page);
  });
});

test('the keyboard opens a task and gets its row back when it closes', async ({
  page,
  authenticate,
  mockApi,
}) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await authenticate({ timezone: 'Europe/Paris' });
  await playTheApi(mockApi);

  await page.goto('/en/dashboard/tools/tasks?list=l1');
  await waitForHydration(page, 'input[type="checkbox"]');
  const link = page.getByRole('link', { name: /Prepare the committee deck/ });
  await link.focus();
  await page.keyboard.press('Enter');

  const back = page.getByRole('button', { name: 'Tasks' });
  await expect(back).toBeFocused();
  await expectNoOverflow(page, 'detail at 390px');
  await page.keyboard.press('Enter');

  await expect(page.getByRole('link', { name: /Prepare the committee deck/ })).toBeFocused();
});

/* PHONE LINES: the owner's remarks of 2026-11-06. */
test('a task on a phone says where it goes back to, and acts as an event does', async ({
  page,
  authenticate,
  mockApi,
}) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await authenticate({ timezone: 'Europe/Paris' });
  await playTheApi(mockApi);

  await page.goto('/en/dashboard/tools/tasks?list=l1');
  await waitForHydration(page, 'input[type="checkbox"]');
  await expect(page.getByText('Completed', { exact: true })).toBeVisible();
  const tool = page.getByRole('region', { name: 'Tasks' });
  await expectLinesCentredIn(
    tool,
    tool.getByRole('switch', { name: 'Completed' }),
    tool.getByText('Completed', { exact: true }),
    tool.getByRole('button', { name: 'Select' }),
    tool.getByRole('button', { name: 'Actions on this list' })
  );
  // « List » is for the ear alone: the eye reads the list's name in the field.
  await expect(page.getByRole('combobox', { name: 'List' })).toBeVisible();
  await expect(page.getByText('List', { exact: true })).toHaveCount(0);

  await page.getByRole('link', { name: /Prepare the committee deck/ }).click();
  const detail = page.getByRole('complementary', { name: 'Detail' });
  const back = detail.getByRole('button', { name: 'Tasks' });
  await expect(back).toBeVisible();
  // The chevron starts where the fields start; the button's own padding is its reach.
  const [chevron, title] = await Promise.all([
    back.locator('svg').boundingBox(),
    detail.getByRole('textbox', { name: 'Title' }).boundingBox(),
  ]);
  expect(Math.abs((chevron?.x ?? 0) - (title?.x ?? 0))).toBeLessThanOrEqual(1);

  const save = detail.getByRole('button', { name: 'Save' });
  const done = detail.getByRole('button', { name: 'Mark as done' });
  const remove = detail.getByRole('button', { name: 'Delete' });
  const ask = detail.getByRole('button', { name: 'Ask LIA' });
  await expectOnOneLine(back, save, done, remove, ask);
  await expectUnder(ask, detail.getByRole('textbox', { name: 'Title' }));
  await expectInside(detail, ask);
  await expectSameStart(back.locator('svg'), detail.getByRole('textbox', { name: 'Title' }));

  // « Save » stands outside the form and still submits it.
  const field = detail.getByRole('textbox', { name: 'Title' });
  await field.fill('Prepare the committee deck, version 2');
  await save.click();
  await expect(detail.getByRole('status')).not.toBeEmpty();
});
