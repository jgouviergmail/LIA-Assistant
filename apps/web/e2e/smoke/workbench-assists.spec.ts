/**
 * What LIA does from the Tools, hermetic (ADR-372).
 *
 * The API is played by the spec, an assist's answer included. Proven at 390 px and on a large
 * screen, in the three themes: the reader's bar keeps its icons, the list stays on the screen, a
 * panel takes no room until it is asked for and leaves when it is closed; a refusal is said in place;
 * the keyboard walks the list; an attachment's row gains no control; a sentence becomes the criteria
 * on screen; the page's order is LIA's only once asked, behind « Filters » on a phone. With the
 * capability off, the Tools are what they were.
 */
import AxeBuilder from '@axe-core/playwright';
import type { Page } from '@playwright/test';

import { test, expect, waitForHydration } from '../fixtures';
import type { MockRoute } from '../fixtures/api-mock';
import { appConfig } from '../fixtures/dashboard-shell';
import { expectNoOverflow, prepareTheme } from './overflow-report';
import { expectInside, expectOnOneLine } from './phone-lines';

const LIMITS = {
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
};

const RAIL = {
  tools: ['mail', 'calendar', 'tasks', 'contacts', 'files', 'lights'].map(tool =>
    tool === 'mail'
      ? {
          tool,
          state: 'ready',
          provider: 'google_gmail',
          features: ['mark_read', 'attachments', 'attachment_filter', 'labels'],
          bounds: { search_max_chars: 500 },
        }
      : { tool, state: 'not_connected', provider: null, features: [], bounds: {} }
  ),
  limits: LIMITS,
};

const FOLDERS = {
  folders: [
    { id: 'system:inbox', kind: 'system', role: 'inbox', name: null },
    { id: 'system:sent', kind: 'system', role: 'sent', name: null },
    { id: 'system:trash', kind: 'system', role: 'trash', name: null },
  ],
};

function row(id: string, subject: string, name: string) {
  return {
    id,
    thread_id: id,
    sender: { name, address: `${id}@example.org` },
    subject,
    snippet: 'A line of it…',
    received_at: new Date().toISOString(),
    is_read: true,
    is_starred: false,
    has_attachments: false,
    label_ids: [],
  };
}

const ROWS = [
  row('m1', 'Committee agenda for Thursday', 'Camille Martin'),
  row('m2', 'Your weekly digest', 'Horizon News'),
  row('m3', 'The contract to sign today', 'Ana Lima'),
];

const MESSAGE = {
  ...ROWS[0],
  reply_to: [],
  to: [{ name: 'Me', address: 'me@example.org' }],
  cc: [],
  body: 'Quarter review at nine. Please bring the figures.',
  attachments: [
    {
      id: 'a1',
      filename: 'a-document-with-a-rather-long-name-for-a-phone.pdf',
      mime_type: 'application/pdf',
      size: 2048,
      previewable: true,
    },
  ],
};

const COST = {
  tokens_in: 120,
  tokens_out: 40,
  tokens_cache: 0,
  cost_eur: 0.0004,
  model_name: 'a-model',
};

const SUMMARY = {
  gist: 'The committee meets on Thursday at nine.',
  key_points: ['Quarter review'],
  actions: ['Bring the figures'],
  category: 'work',
  importance: 'high',
  usage: COST,
};

interface Played {
  summaries: number;
  listed: string[];
  triages: unknown[];
}

async function playTheApi(
  mockApi: (routes: MockRoute[]) => Promise<void>,
  options: { assists?: boolean; summary?: 'refused' } = {}
): Promise<Played> {
  const played: Played = { summaries: 0, listed: [], triages: [] };
  const assists = options.assists ?? true;
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
    { url: /\/api\/v1\/workbench\/mail\/folders$/, json: FOLDERS },
    {
      url: /\/api\/v1\/workbench\/mail\/counts$/,
      method: 'GET',
      json: { counts: {}, truncated: false },
    },
    {
      url: /\/api\/v1\/workbench\/mail\/messages(\?.*)?$/,
      method: 'GET',
      handler: async route => {
        played.listed.push(new URL(route.request().url()).search);
        await route.fulfill({ json: { items: ROWS, next_page_token: null, skipped: 0 } });
      },
    },
    { url: /\/api\/v1\/workbench\/mail\/message\?/, method: 'GET', json: MESSAGE },
    {
      url: /\/api\/v1\/workbench\/mail\/conversation\?/,
      method: 'GET',
      json: { items: [], truncated: false },
    },
    {
      url: /\/api\/v1\/workbench\/mail\/message\/html\?/,
      method: 'GET',
      json: { html: null, truncated: false },
    },
    {
      url: /\/api\/v1\/tool-assists\/mail\/summary$/,
      method: 'POST',
      handler: async route => {
        played.summaries += 1;
        if (options.summary === 'refused') {
          await route.fulfill({ status: 429, json: { detail: { code: 'assist_quota' } } });
          return;
        }
        await route.fulfill({ json: SUMMARY });
      },
    },
    {
      url: /\/api\/v1\/workbench\/mail\/signature$/,
      method: 'GET',
      json: { text: '', block: '' },
    },
    {
      url: /\/api\/v1\/workbench\/mail\/reply-recipients\?/,
      method: 'GET',
      json: { to: [{ name: 'Camille', address: 'camille@example.org' }], cc: [] },
    },
    {
      url: /\/api\/v1\/tool-assists\/mail\/reply$/,
      method: 'POST',
      json: {
        text: 'Thank you, I will bring the figures.',
        subject: null,
        cut: false,
        usage: COST,
      },
    },
    {
      url: /\/api\/v1\/tool-assists\/mail\/search$/,
      method: 'POST',
      json: {
        search: {
          words: 'from:Ana contract',
          unread: true,
          attachments: false,
          first_day: null,
          last_day: null,
        },
        usage: COST,
      },
    },
    {
      url: /\/api\/v1\/tool-assists\/mail\/triage$/,
      method: 'POST',
      handler: async route => {
        played.triages.push(route.request().postDataJSON());
        await route.fulfill({
          json: {
            items: [
              { id: 'm1', importance: 'normal', category: 'work' },
              { id: 'm2', importance: 'low', category: 'newsletter' },
              { id: 'm3', importance: 'high', category: 'work' },
            ],
            skipped: 0,
            usage: COST,
          },
        });
      },
    },
  ]);
  return played;
}

async function openList(page: Page, reader: ReturnType<Page['getByRole']>) {
  await reader.getByRole('button', { name: 'Ask LIA' }).click();
  await expect(page.getByRole('menuitem', { name: 'Sum it up' })).toBeVisible();
}

for (const sample of [
  { width: 1280, theme: 'light' },
  { width: 390, theme: 'dark' },
  { width: 390, theme: 'oled' },
] as const) {
  test(`a message is summed up in place at ${sample.width}px in ${sample.theme}`, async ({
    page,
    authenticate,
    mockApi,
  }) => {
    await page.setViewportSize({ width: sample.width, height: 844 });
    await prepareTheme(page, sample.theme);
    await authenticate({ timezone: 'Europe/Paris' });
    const played = await playTheApi(mockApi);

    await page.goto('/en/dashboard/tools/mail?id=m1');
    const reader = page.getByRole('article', { name: 'Committee agenda for Thursday' });
    await expect(reader.getByText('Quarter review', { exact: false })).toBeVisible();
    await expect(reader.getByRole('region', { name: 'Summary' })).toHaveCount(0);

    await expectOnOneLine(
      reader.getByRole('button', { name: 'Delete' }),
      reader.getByRole('button', { name: 'Ask LIA' })
    );
    await openList(page, reader);
    await expectInside(page.locator('body'), page.getByRole('menu'));
    await page.getByRole('menuitem', { name: 'Sum it up' }).click();

    const panel = reader.getByRole('region', { name: 'Summary' });
    await expect(panel.getByText('The committee meets on Thursday at nine.')).toBeVisible();
    await expect(panel.getByText('Bring the figures')).toBeVisible();
    await expect(panel.getByText(/€/)).toBeVisible();
    expect(played.summaries).toBe(1);
    await expectNoOverflow(page, `summary ${sample.width}px ${sample.theme}`);
    expect((await new AxeBuilder({ page }).include('main').analyze()).violations).toEqual([]);

    await panel.getByRole('button', { name: 'Close' }).click();
    await expect(panel).toHaveCount(0);
  });
}

test('a refusal is said in its place, and the person can try again', async ({
  page,
  authenticate,
  mockApi,
}) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await authenticate({ timezone: 'Europe/Paris' });
  const played = await playTheApi(mockApi, { summary: 'refused' });

  await page.goto('/en/dashboard/tools/mail?id=m1');
  const reader = page.getByRole('article', { name: 'Committee agenda for Thursday' });
  await openList(page, reader);
  await page.getByRole('menuitem', { name: 'Sum it up' }).click();

  const panel = reader.getByRole('region', { name: 'Summary' });
  await expect(panel.getByRole('alert')).toBeVisible();
  await panel.getByRole('button', { name: 'Try again' }).click();
  await expect.poll(() => played.summaries).toBe(2);
});

test('the keyboard walks the list and gets back to its icon', async ({
  page,
  authenticate,
  mockApi,
}) => {
  await page.setViewportSize({ width: 1280, height: 900 });
  await authenticate({ timezone: 'Europe/Paris' });
  await playTheApi(mockApi);

  await page.goto('/en/dashboard/tools/mail?id=m1');
  const reader = page.getByRole('article', { name: 'Committee agenda for Thursday' });
  const icon = reader.getByRole('button', { name: 'Ask LIA' });
  await icon.focus();
  await page.keyboard.press('Enter');
  await expect(page.getByRole('menu')).toBeVisible();
  await page.keyboard.press('Escape');

  await expect(page.getByRole('menu')).toHaveCount(0);
  await expect(icon).toBeFocused();
});

test('an attachment’s row keeps its width: one icon holds what LIA and the drive offer', async ({
  page,
  authenticate,
  mockApi,
}) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await authenticate({ timezone: 'Europe/Paris' });
  await playTheApi(mockApi);

  await page.goto('/en/dashboard/tools/mail?id=m1');
  const reader = page.getByRole('article', { name: 'Committee agenda for Thursday' });
  const list = reader.getByRole('region', { name: /attachment/i });
  const menu = list.getByRole('button', { name: /What to do with/ });
  await expect(menu).toBeVisible();
  await expectInside(reader, menu);
  await expectNoOverflow(page, 'an attachment on a phone');

  await menu.click();
  await expect(page.getByRole('menuitem', { name: 'Summarize' })).toBeVisible();
});

test('a proposed reply is read first, and joins the message only on the person’s word', async ({
  page,
  authenticate,
  mockApi,
}) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await authenticate({ timezone: 'Europe/Paris' });
  await playTheApi(mockApi);

  await page.goto('/en/dashboard/tools/mail?id=m1');
  const reader = page.getByRole('article', { name: 'Committee agenda for Thursday' });
  await openList(page, reader);
  await page.getByRole('menuitem', { name: 'Propose a reply' }).click();

  const proposal = page.getByRole('dialog', { name: 'Propose a reply' });
  await expect(proposal).toBeVisible();
  await expect(proposal.getByText('Thank you, I will bring the figures.')).toBeVisible();
  await expectNoOverflow(page, 'a proposal on a phone');

  await proposal.getByRole('button', { name: 'Use this text' }).click();
  await expect(proposal).toHaveCount(0);
  await expect(page.getByText('Thank you, I will bring the figures.').first()).toBeVisible();
});

test('a sentence becomes the criteria on screen, which the person can change', async ({
  page,
  authenticate,
  mockApi,
}) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await authenticate({ timezone: 'Europe/Paris' });
  const played = await playTheApi(mockApi);

  await page.goto('/en/dashboard/tools/mail');
  await waitForHydration(page, 'a[data-mail-row]');
  const box = page.getByRole('searchbox');
  const read = page.getByRole('button', { name: 'Read this sentence as a search' });

  await box.fill('contract');
  await expect(read).toHaveCount(0);
  await box.fill('the unread contract from Ana');
  await read.click();

  await expect(box).toHaveValue('from:Ana contract');
  await expect.poll(() => played.listed.at(-1)).toContain('from%3AAna');
  await expectNoOverflow(page, 'a search read from a sentence');
});

test('the page is weighed once asked, and a phone keeps the chip behind « Filters »', async ({
  page,
  authenticate,
  mockApi,
}) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await authenticate({ timezone: 'Europe/Paris' });
  const played = await playTheApi(mockApi);

  await page.goto('/en/dashboard/tools/mail');
  await waitForHydration(page, 'a[data-mail-row]');
  const sort = page.getByRole('button', { name: 'Sort' });
  await expect(sort).toBeHidden();
  expect(played.triages).toEqual([]);

  await page.getByRole('button', { name: /filter/i }).click();
  await sort.click();
  await page.getByRole('menuitemradio', { name: 'Important first' }).click();

  await expect(page.locator('a[data-mail-row]').first()).toContainText(
    'The contract to sign today'
  );
  expect(played.triages).toEqual([{ message_ids: ['m1', 'm2', 'm3'] }]);
  await expectNoOverflow(page, 'a page weighed on a phone');
});

test('switched off, the Tools are what they were', async ({ page, authenticate, mockApi }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await authenticate({ timezone: 'Europe/Paris' });
  await playTheApi(mockApi, { assists: false });

  await page.goto('/en/dashboard/tools/mail?id=m1');
  const reader = page.getByRole('article', { name: 'Committee agenda for Thursday' });
  await reader.getByRole('button', { name: 'Ask LIA' }).click();

  await expect(page.getByRole('menuitem', { name: 'Remind me' })).toBeVisible();
  await expect(page.getByRole('menuitem', { name: 'Sum it up' })).toHaveCount(0);
  await page.keyboard.press('Escape');
  await page.goto('/en/dashboard/tools/mail');
  await waitForHydration(page, 'a[data-mail-row]');
  await page.getByRole('button', { name: /filter/i }).click();
  await expect(page.getByRole('button', { name: 'Sort' })).toHaveCount(0);
});
