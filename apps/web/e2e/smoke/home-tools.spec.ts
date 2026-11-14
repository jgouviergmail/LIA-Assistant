/**
 * The home's cards and the « Tools », hermetic (owner, 2026-11-07).
 *
 * Where the instance offers the Tools, a task of the home opens in its own list there, « done »
 * acts from the card through the Tools' route and the card is read again, and a message's menu
 * holds its five acts, direct ones first — at 390 px in OLED too, with no horizontal scroll and an
 * axe-clean open menu.
 */
import AxeBuilder from '@axe-core/playwright';
import type { Page } from '@playwright/test';

import { test, expect, waitForHydration } from '../fixtures';
import type { MockRoute } from '../fixtures/api-mock';
import { HOME_TIMEZONE, homeBriefing, homeItemName, homeRoutes } from '../fixtures/dashboard-home';
import { appConfig } from '../fixtures/dashboard-shell';
import { expectNoOverflow, prepareTheme } from './overflow-report';

const LIST = 'list-home';
const LIST_NAME = 'Household';

/** The home's payload, its tasks and messages named by their ids as the API now sends them. */
function toolsBriefing() {
  const briefing = homeBriefing();
  const tasks = briefing.cards.tasks.data!;
  tasks.items = tasks.items.map((task, index) => ({
    ...task,
    id: `task-${index}`,
    list_id: LIST,
    list_name: LIST_NAME,
  }));
  const mails = briefing.cards.mails.data!;
  mails.items = mails.items.map((mail, index) => ({ ...mail, id: `mail-${index}` }));
  return briefing;
}

const RAIL = {
  tools: ['mail', 'calendar', 'tasks', 'contacts', 'files', 'lights'].map(tool =>
    tool === 'tasks' || tool === 'mail'
      ? {
          tool,
          state: 'ready',
          provider: tool === 'tasks' ? 'google_tasks' : 'google_gmail',
          features: tool === 'tasks' ? ['due_date_only', 'list_management', 'subtasks'] : [],
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

/** The task the home opens, as the tasks tool reads it. */
function toolTask(index: number) {
  return {
    id: `task-${index}`,
    title: homeItemName('tasks', index),
    notes: null,
    completed: false,
    due: '2026-10-16',
    parent: null,
    position: String(index),
    steps: [],
    importance: null,
    reminder: null,
    repeat: null,
  };
}

/** The Tools offered, the tasks tool's routes played, every PATCH kept for the oracle. */
function toolsRoutes(patched: unknown[]): MockRoute[] {
  return [
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
      json: { items: [{ id: LIST, title: 'Home', default: true }], next_page_token: null },
    },
    {
      url: '**/api/v1/workbench/tasks*',
      method: 'GET',
      json: { items: [toolTask(0), toolTask(1)], next_page_token: null },
    },
    {
      url: '**/api/v1/workbench/tasks',
      method: 'PATCH',
      handler: async route => {
        const change = route.request().postDataJSON() as { task_id: string };
        patched.push(change);
        await route.fulfill({ json: { ...toolTask(0), ...change } });
      },
    },
  ];
}

async function readyHome(page: Page) {
  await page.goto('/en/dashboard');
  await waitForHydration(page, 'main');
  await expect(page.getByText(homeItemName('tasks', 0), { exact: true })).toBeVisible();
}

test('a task of the home opens in its own list in the tasks tool', async ({
  page,
  authenticate,
  mockApi,
}) => {
  await page.setViewportSize({ width: 1280, height: 900 });
  const user = await authenticate({ language: 'en', timezone: HOME_TIMEZONE });
  await mockApi([...homeRoutes(user, toolsBriefing()), ...toolsRoutes([])]);
  await readyHome(page);

  // The card gathers every list (2026-11-10): each task names its own in a badge.
  const opens = page.getByRole('link', { name: `Open the task “${homeItemName('tasks', 0)}”` });
  await expect(opens.getByTitle(LIST_NAME)).toBeVisible();
  await opens.click();

  await expect(page).toHaveURL(/\/en\/dashboard\/tools\/tasks\?list=list-home&task=task-0$/);
  const detail = page.getByRole('complementary', { name: 'Detail' });
  await expect(detail.getByRole('textbox', { name: 'Title' })).toHaveValue(
    homeItemName('tasks', 0)
  );
});

test('« done » acts from the card, then the card is read again', async ({
  page,
  authenticate,
  mockApi,
}) => {
  await page.setViewportSize({ width: 1280, height: 900 });
  const user = await authenticate({ language: 'en', timezone: HOME_TIMEZONE });
  const patched: unknown[] = [];
  const refreshed: string[] = [];
  const after = toolsBriefing();
  after.cards.tasks.data!.items = after.cards.tasks.data!.items.slice(1);
  await mockApi([
    ...homeRoutes(user, toolsBriefing()),
    ...toolsRoutes(patched),
    {
      url: /\/api\/v1\/briefing\/sections\/tasks\/refresh$/,
      method: 'POST',
      handler: async route => {
        refreshed.push(route.request().url());
        await route.fulfill({ json: after.cards.tasks });
      },
    },
  ]);
  await readyHome(page);

  const row = page.getByRole('listitem').filter({ hasText: homeItemName('tasks', 0) });
  await row.getByRole('button', { name: 'More actions' }).click();
  await page.getByRole('menuitem', { name: 'Mark as done' }).click();

  await expect(page.getByText('Task done')).toBeVisible();
  expect(patched).toEqual([{ list_id: LIST, task_id: 'task-0', completed: true }]);
  await expect.poll(() => refreshed.length).toBeGreaterThan(0);
  await expect(page.getByText(homeItemName('tasks', 0), { exact: true })).toHaveCount(0);
});

test('a message’s five acts fit a phone in OLED, axe-clean', async ({
  page,
  authenticate,
  mockApi,
}) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await prepareTheme(page, 'oled');
  const user = await authenticate({ language: 'en', timezone: HOME_TIMEZONE });
  await mockApi([...homeRoutes(user, toolsBriefing()), ...toolsRoutes([])]);
  await readyHome(page);

  const row = page.getByRole('listitem').filter({ hasText: homeItemName('mails', 0) });
  await row.getByRole('button', { name: 'More actions' }).click();
  const menu = page.getByRole('menu');
  await expect(menu.getByRole('menuitem')).toHaveCount(5);
  await expect(menu.getByRole('menuitem').first()).toHaveText('Mark as read');
  await expect(menu.getByRole('menuitem').nth(1)).toHaveText('Archive');

  await expectNoOverflow(page, '390px oled, a message menu open');
  const scan = await new AxeBuilder({ page }).include('[role="menu"]').analyze();
  expect(scan.violations).toEqual([]);
});
