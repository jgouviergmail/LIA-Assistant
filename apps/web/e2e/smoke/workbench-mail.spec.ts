/**
 * The « Tools » mail screen, hermetic (ADR-369, Task 4.7).
 *
 * The API is played by the spec: one ready Gmail mailbox, its folders and a
 * label, a page that says more exists and one hit it could not read, an unread
 * and a starred message, a message with an attachment. Proven at 1280 (three
 * panes) and 390 px, in light, dark and OLED: no horizontal scroll, axe clean
 * on the list and on the reader; a selection is trashed and what could not be
 * is said; a message is sent once; when nobody knows whether it left, the words
 * stay and the person is told to look in Sent; the keyboard walks the list,
 * opens a message and gets its row back when Escape closes it.
 */
import AxeBuilder from '@axe-core/playwright';

import { test, expect, waitForHydration } from '../fixtures';
import type { MockRoute } from '../fixtures/api-mock';
import { appConfig } from '../fixtures/dashboard-shell';
import { expectNoOverflow, prepareTheme } from './overflow-report';

const RAIL = {
  tools: ['mail', 'calendar', 'tasks', 'contacts', 'files', 'lights'].map(tool =>
    tool === 'mail'
      ? {
          tool,
          state: 'ready',
          provider: 'google_gmail',
          features: [
            'mark_read',
            'drafts',
            'attachments',
            'attachment_filter',
            'labels',
            'vacation',
            'filters',
          ],
          bounds: {
            search_max_chars: 500,
            recipient_query_min_chars: 2,
            recipients_max: 100,
            recipient_max_chars: 320,
            subject_max_chars: 998,
            body_max_chars: 100000,
            attachments_max: 10,
            attachments_max_bytes: 26214400,
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

const FOLDERS = {
  folders: [
    { id: 'system:inbox', kind: 'system', role: 'inbox', name: null },
    { id: 'system:starred', kind: 'system', role: 'starred', name: null },
    { id: 'system:sent', kind: 'system', role: 'sent', name: null },
    { id: 'system:drafts', kind: 'system', role: 'drafts', name: null },
    { id: 'system:spam', kind: 'system', role: 'spam', name: null },
    { id: 'system:trash', kind: 'system', role: 'trash', name: null },
    { id: 'Label_7', kind: 'user', role: null, name: 'Work' },
    { id: 'Label_8', kind: 'user', role: null, name: 'Home' },
  ],
};

const NOW = Date.now();
const hoursAgo = (hours: number) => new Date(NOW - hours * 3600_000).toISOString();

const ROWS = [
  {
    id: 'm1',
    thread_id: 'm1',
    sender: { name: 'Camille Martin', address: 'camille@example.org' },
    subject: 'Committee agenda for Thursday',
    snippet: 'Hello everyone, here is the proposed agenda…',
    received_at: hoursAgo(1),
    is_read: false,
    is_starred: true,
    label_ids: ['Label_7'],
  },
  {
    id: 'm2',
    thread_id: 'm2',
    sender: { name: 'Horizon Bank', address: 'statements@example.org' },
    subject: 'Your October statement is available',
    snippet: 'Your account statement for October…',
    received_at: hoursAgo(3),
    is_read: false,
    is_starred: false,
    label_ids: [],
  },
  {
    id: 'm3',
    thread_id: 'm3',
    sender: { name: 'Product team', address: 'product@example.org' },
    subject: 'Minutes — sprint review 22',
    snippet: 'Thanks to all for the demo. The three topics…',
    received_at: hoursAgo(30),
    is_read: true,
    is_starred: false,
    label_ids: ['Label_7'],
  },
  {
    id: 'm4',
    thread_id: 'm4',
    sender: { name: 'Theo Lambert', address: 'theo@example.org' },
    subject: 'Re: Mountain weekend',
    snippet: 'Perfect for the hut! I am booking the places…',
    received_at: hoursAgo(50),
    is_read: true,
    is_starred: false,
    label_ids: ['Label_8'],
  },
];

const MESSAGE = {
  ...ROWS[0],
  reply_to: [],
  to: [{ name: '', address: 'me@example.org' }],
  cc: [{ name: 'Theo Lambert', address: 'theo@example.org' }],
  body: 'Hello everyone,\n\nHere is the proposed agenda for Thursday, 3 pm:\n1. Quarter review\n2. 2027 budget\n3. Delivery calendar\n\nTell me by Wednesday evening if anything is missing.',
  attachments: [
    { id: 'ANGj1', filename: 'agenda.pdf', mime_type: 'application/pdf', size: 186368 },
    {
      id: 'ANGj2',
      filename: 'budget-2027.xlsx',
      mime_type: 'application/vnd.ms-excel',
      size: 65536,
    },
  ],
};

interface Played {
  sends: number;
}

async function playTheApi(
  mockApi: (routes: MockRoute[]) => Promise<void>,
  options: { send?: 'ok' | 'unknown'; html?: string } = {}
): Promise<Played> {
  const played: Played = { sends: 0 };
  await mockApi([
    {
      url: '**/api/v1/config',
      json: {
        ...appConfig,
        features: { ...appConfig.features, workbench_enabled: true },
        capabilities: { workbench: { enabled: true, family: 'work' } },
      },
    },
    {
      url: '**/api/v1/workbench',
      json: {
        ...RAIL,
        tools: RAIL.tools.map(tool =>
          tool.tool === 'mail' && options.html !== undefined
            ? { ...tool, features: [...tool.features, 'html'] }
            : tool
        ),
      },
    },
    { url: /\/api\/v1\/workbench\/mail\/folders$/, json: FOLDERS },
    {
      url: /\/api\/v1\/workbench\/mail\/messages(\?.*)?$/,
      method: 'GET',
      json: { items: ROWS, next_page_token: 'p2', skipped: 1 },
    },
    { url: /\/api\/v1\/workbench\/mail\/message\?/, method: 'GET', json: MESSAGE },
    {
      url: /\/api\/v1\/workbench\/mail\/message\/html\?/,
      method: 'GET',
      json: { html: options.html ?? null, truncated: false },
    },
    {
      url: /\/api\/v1\/workbench\/mail\/read-state$/,
      method: 'POST',
      handler: async route => {
        const asked = route.request().postDataJSON() as { message_ids: string[] };
        await route.fulfill({ json: { done: asked.message_ids, failed: [] } });
      },
    },
    {
      url: /\/api\/v1\/workbench\/mail\/trash$/,
      method: 'POST',
      handler: async route => {
        const [first, ...others] = (route.request().postDataJSON() as { message_ids: string[] })
          .message_ids;
        await route.fulfill({
          json: { done: [first], failed: others.map(id => ({ id, status: 'failed' })) },
        });
      },
    },
    {
      url: /\/api\/v1\/workbench\/mail\/recipients\?/,
      method: 'GET',
      handler: async route => {
        const query = new URL(route.request().url()).searchParams.get('q') ?? '';
        await route.fulfill({
          json: {
            query,
            suggestions: [{ name: 'Ana Lima', email: 'ana@example.org' }],
            truncated: false,
          },
        });
      },
    },
    {
      url: /\/api\/v1\/workbench\/mail\/send$/,
      method: 'POST',
      handler: async route => {
        played.sends += 1;
        if (options.send === 'unknown') {
          await route.fulfill({ status: 504, json: { detail: { code: 'outcome_unknown' } } });
          return;
        }
        await route.fulfill({ json: { id: 's1', thread_id: 't9' } });
      },
    },
  ]);
  return played;
}

for (const sample of [
  { width: 1280, theme: 'light' },
  { width: 1280, theme: 'dark' },
  { width: 390, theme: 'oled' },
] as const) {
  test(`mail screen at ${sample.width}px in ${sample.theme}`, async ({
    page,
    authenticate,
    mockApi,
  }) => {
    await page.setViewportSize({ width: sample.width, height: 900 });
    await prepareTheme(page, sample.theme);
    await authenticate({ timezone: 'Europe/Paris' });
    await playTheApi(mockApi);

    await page.goto('/en/dashboard/tools/mail');
    await waitForHydration(page, 'a[data-mail-row]');
    await expect(page.getByText('Your October statement is available')).toBeVisible();
    await expect(page.getByRole('button', { name: 'Older messages' })).toBeVisible();
    await expect(
      page.getByText('1 message could not be read: this page is partial.')
    ).toBeVisible();
    await expectNoOverflow(page, `list ${sample.width}px ${sample.theme}`);
    expect((await new AxeBuilder({ page }).include('main').analyze()).violations).toEqual([]);

    await page.goto('/en/dashboard/tools/mail?id=m1');
    const reader = page.getByRole('article', { name: 'Committee agenda for Thursday' });
    await expect(reader.getByText('Quarter review', { exact: false })).toBeVisible();
    await expect(reader.getByRole('link', { name: /agenda\.pdf/ })).toBeVisible();
    await expectNoOverflow(page, `reader ${sample.width}px ${sample.theme}`);
    expect((await new AxeBuilder({ page }).include('main').analyze()).violations).toEqual([]);
  });
}

test('the original layout cannot navigate even with an explicit sender target', async ({
  page,
  authenticate,
  mockApi,
}) => {
  await authenticate({ timezone: 'Europe/Paris' });
  await playTheApi(mockApi, {
    html:
      '<p>Readable original</p><img src="https://www.google.com/mail-image-probe">' +
      '<a href="https://www.google.com/mail-link-probe" target="_self">Explicit target</a>' +
      '<noscript><a href="https://www.google.com/mail-link-probe" target="_self">No script target</a></noscript>' +
      '<script>window.parent.postMessage("mail-script-ran", "*")</script>',
  });
  const requests: string[] = [];
  await page.route('https://www.google.com/mail-*-probe', async route => {
    requests.push(route.request().url());
    await route.abort();
  });
  await page.goto('/en/dashboard/tools/mail?id=m1');
  const original = page.frameLocator('iframe[sandbox=""]');
  await expect(original.getByText('Readable original')).toBeVisible();
  await original.getByText('Explicit target', { exact: true }).click();
  await expect(original.getByText('Readable original')).toBeVisible();
  await original.getByText('No script target', { exact: true }).click();
  await expect(original.getByText('Readable original')).toBeVisible();
  expect(requests).toEqual([]);
});

test('a selection is trashed and what could not be is said', async ({
  page,
  authenticate,
  mockApi,
}) => {
  await page.setViewportSize({ width: 1280, height: 900 });
  await authenticate({ timezone: 'Europe/Paris' });
  await playTheApi(mockApi);

  await page.goto('/en/dashboard/tools/mail');
  await waitForHydration(page, 'a[data-mail-row]');
  await page
    .getByRole('checkbox', {
      name: 'Select the message from Camille Martin: Committee agenda for Thursday',
    })
    .check();
  await page
    .getByRole('checkbox', {
      name: 'Select the message from Horizon Bank: Your October statement is available',
    })
    .check();
  const bar = page.getByRole('region', { name: 'Selected messages' });
  await expect(bar.getByText('2 selected')).toBeVisible();
  await bar.getByRole('button', { name: 'Move to the trash' }).click();

  await expect(page.getByText('Done for 1, not for 1: those stay listed.')).toBeVisible();
  await expect(page.getByText('Committee agenda for Thursday')).toHaveCount(0);
  await expect(page.getByText('Your October statement is available')).toBeVisible();
});

test('a message is sent once, and the composer closes saying it left', async ({
  page,
  authenticate,
  mockApi,
}) => {
  await page.setViewportSize({ width: 1280, height: 900 });
  await authenticate({ timezone: 'Europe/Paris' });
  const played = await playTheApi(mockApi);

  await page.goto('/en/dashboard/tools/mail');
  await waitForHydration(page, 'a[data-mail-row]');
  await page
    .getByRole('navigation', { name: 'Folders' })
    .getByRole('button', { name: 'New message' })
    .click();
  const dialog = page.getByRole('dialog', { name: 'New message' });
  await dialog.getByRole('combobox', { name: 'To' }).fill('ana@example.org');
  await dialog.getByRole('textbox', { name: 'Subject' }).fill('Thursday');
  await dialog.getByRole('textbox', { name: 'Message' }).fill('See you there.');
  await dialog.getByRole('button', { name: 'Send' }).dblclick();

  // The toast, not the « Sent » folder of the same name.
  await expect(
    page.locator('[data-sonner-toast]').getByText('Sent', { exact: true })
  ).toBeVisible();
  await expect(dialog).toHaveCount(0);
  expect(played.sends).toBe(1);
});

test('when nobody knows whether it left, the words stay and Sent is named', async ({
  page,
  authenticate,
  mockApi,
}) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await authenticate({ timezone: 'Europe/Paris' });
  const played = await playTheApi(mockApi, { send: 'unknown' });

  await page.goto('/en/dashboard/tools/mail');
  await waitForHydration(page, 'a[data-mail-row]');
  await page.getByRole('button', { name: 'New message' }).first().click();
  const dialog = page.getByRole('dialog', { name: 'New message' });
  await dialog.getByRole('combobox', { name: 'To' }).fill('ana@example.org');
  await dialog.getByRole('textbox', { name: 'Message' }).fill('See you there.');
  await dialog.getByRole('button', { name: 'Send' }).click();

  await expect(dialog.getByRole('alert')).toContainText('Look in Sent');
  await expect(dialog.getByRole('textbox', { name: 'Message' })).toHaveValue('See you there.');
  // The same words are not sent again while nobody knows whether they left: the
  // button says so (aria-disabled), and a click on it sends nothing.
  const send = dialog.getByRole('button', { name: 'Send' });
  await expect(send).toHaveAttribute('aria-disabled', 'true');
  await send.click({ force: true });
  expect(played.sends).toBe(1);
  await expectNoOverflow(page, 'composer at 390px');
});

test('the keyboard walks the list, opens a message and gets its row back on Escape', async ({
  page,
  authenticate,
  mockApi,
}) => {
  await page.setViewportSize({ width: 1280, height: 900 });
  await authenticate({ timezone: 'Europe/Paris' });
  await playTheApi(mockApi);

  await page.goto('/en/dashboard/tools/mail');
  await waitForHydration(page, 'a[data-mail-row]');
  await page.getByRole('link', { name: /Committee agenda for Thursday/ }).focus();
  await page.keyboard.press('ArrowDown');
  await expect(page.getByRole('link', { name: /Your October statement/ })).toBeFocused();
  await page.keyboard.press('ArrowUp');
  await page.keyboard.press('Enter');

  await expect(page).toHaveURL(/\/en\/dashboard\/tools\/mail\?id=m1$/);
  const reader = page.getByRole('article', { name: 'Committee agenda for Thursday' });
  await reader.getByRole('button', { name: 'Close the message' }).focus();
  await page.keyboard.press('Escape');

  await expect(page).toHaveURL(/\/en\/dashboard\/tools\/mail$/);
  await expect(page.getByRole('link', { name: /Committee agenda for Thursday/ })).toBeFocused();
});
