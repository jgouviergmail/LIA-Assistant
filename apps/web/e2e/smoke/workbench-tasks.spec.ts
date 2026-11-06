/**
 * The « Tools » tasks screen, hermetic (ADR-369, Task 6.2).
 *
 * The API is played by the spec: one ready tasks provider, two lists, a page
 * that says more exists, a subtask, a due day today and one overdue. Proven at
 * 1280 and 390 px, in light, dark and OLED: no horizontal scroll, axe clean on
 * the screen; a refused completion is rolled back and said in the refusal's
 * own words; the keyboard opens a task and gets its row back when it closes.
 */
import AxeBuilder from '@axe-core/playwright';

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
        ],
        next_page_token: null,
      },
    },
    { url: '**/api/v1/workbench/tasks/view*', method: 'GET', json: VIEW },
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

    await page.goto('/en/dashboard/tools/tasks');
    await waitForHydration(page, 'input[type="checkbox"]');
    await expect(page.getByText('Call the plumber')).toBeVisible();
    await expect(page.getByRole('button', { name: 'Load more' })).toBeVisible();

    await expectNoOverflow(page, `${sample.width}px ${sample.theme}`);
    const scan = await new AxeBuilder({ page }).include('main').analyze();
    expect(scan.violations).toEqual([]);
  });
}

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

test('ticked tasks go to another list, and leave this one', async ({
  page,
  authenticate,
  mockApi,
}) => {
  await page.setViewportSize({ width: 1280, height: 900 });
  await authenticate({ timezone: 'Europe/Paris' });
  await playTheApi(mockApi);

  await page.goto('/en/dashboard/tools/tasks');
  await waitForHydration(page, 'input[type="checkbox"]');
  await page.getByRole('button', { name: 'Select' }).click();
  await page.getByRole('checkbox', { name: 'Select: Send back the insurance form' }).check();

  const bar = page.getByRole('region', { name: 'Selected tasks' });
  await expect(bar).toBeVisible();
  const scan = await new AxeBuilder({ page }).include('main').analyze();
  expect(scan.violations).toEqual([]);

  await bar.getByRole('combobox', { name: 'Move to a list' }).selectOption({ label: 'Groceries' });

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

  await page.goto('/en/dashboard/tools/tasks');
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

  await page.goto('/en/dashboard/tools/tasks');
  await waitForHydration(page, 'input[type="checkbox"]');
  const box = page.getByRole('checkbox', { name: 'Mark as done: Call the plumber' });
  await box.click();

  await expect(page.getByText('The service is not answering: try again later.')).toBeVisible();
  await expect(box).not.toBeChecked();
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

  const back = page.getByRole('button', { name: 'Back to the list' });
  await expect(back).toBeFocused();
  await expectNoOverflow(page, 'detail at 390px');
  await page.keyboard.press('Enter');

  await expect(page.getByRole('link', { name: /Prepare the committee deck/ })).toBeFocused();
});
