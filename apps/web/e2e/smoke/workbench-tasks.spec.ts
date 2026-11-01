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
    calendar_window_max_events: 500,
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
  },
  {
    id: 't2',
    title: 'Prepare the committee deck',
    notes: 'Ten slides at most.',
    completed: false,
    due: shifted(4),
    parent: null,
    position: '2',
  },
  {
    id: 't2a',
    title: 'Gather the quarter figures',
    notes: null,
    completed: false,
    due: null,
    parent: 't2',
    position: '1',
  },
  {
    id: 't3',
    title: 'Call the plumber',
    notes: null,
    completed: false,
    due: shifted(-2),
    parent: null,
    position: '3',
  },
];

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
