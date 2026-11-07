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
 * opens a message and gets its row back when Escape closes it. A conversation
 * is walked from the band above the message, the focus staying on its link, and
 * the list draws one as a line whose acts reach every message loaded under it.
 */
import { readFileSync } from 'node:fs';
import { join } from 'node:path';

import AxeBuilder from '@axe-core/playwright';
import type { Locator, Page } from '@playwright/test';

import { test, expect, waitForHydration } from '../fixtures';
import type { MockRoute } from '../fixtures/api-mock';
import { appConfig } from '../fixtures/dashboard-shell';
import { expectNoOverflow, prepareTheme } from './overflow-report';
import {
  expectInside,
  expectLinesCentredIn,
  expectOnOneLine,
  expectSameCentre,
  expectSameEnd,
  expectNoZoomOnFocus,
  expectSameStart,
  expectStackedWhole,
  expectUnder,
  wordStartOf,
} from './phone-lines';

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
            'vacation_subject',
            'vacation_open_end',
            'filters',
            'filter_words',
          ],
          bounds: {
            search_max_chars: 500,
            assist_text_max_chars: 8000,
            assist_instruction_max_chars: 500,
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
    upload_max_bytes: 26214400,
    calendar_window_max_events: 500,
    send_undo_seconds: 0,
    draft_autosave_seconds: 0,
    search_max_chars: 500,
    assist_text_max_chars: 8000,
    assist_instruction_max_chars: 500,
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
    has_attachments: true,
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
    has_attachments: false,
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
    has_attachments: false,
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
    has_attachments: false,
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
      previewable: true,
    },
  ],
};

interface Played {
  sends: number;
  /** Each move the screen asked, in order. */
  moves: { message_ids: string[]; to: string; origin?: string }[];
  /** What each send, reply and draft save carried. */
  bodies: Record<string, unknown>[];
  replies: Record<string, unknown>[];
  drafts: Record<string, unknown>[];
  signature: string;
}

async function playTheApi(
  mockApi: (routes: MockRoute[]) => Promise<void>,
  options: {
    send?: 'ok' | 'unknown';
    html?: string;
    undoSeconds?: number;
    autosaveSeconds?: number;
    rows?: typeof ROWS;
    conversation?: { items: typeof ROWS; truncated: boolean };
    assists?: boolean;
  } = {}
): Promise<Played> {
  const played: Played = {
    sends: 0,
    moves: [],
    bodies: [],
    replies: [],
    drafts: [],
    signature: '',
  };
  await mockApi([
    {
      url: '**/api/v1/config',
      json: {
        ...appConfig,
        features: {
          ...appConfig.features,
          workbench_enabled: true,
          tool_assists_enabled: options.assists ?? false,
        },
        capabilities: {
          workbench: { enabled: true, family: 'work' },
          tool_assists: { enabled: options.assists ?? false, family: 'work' },
        },
      },
    },
    {
      url: '**/api/v1/workbench',
      json: {
        ...RAIL,
        limits: {
          ...RAIL.limits,
          send_undo_seconds: options.undoSeconds ?? 0,
          draft_autosave_seconds: options.autosaveSeconds ?? 0,
          search_max_chars: 500,
          assist_text_max_chars: 8000,
          assist_instruction_max_chars: 500,
        },
        tools: RAIL.tools.map(tool =>
          tool.tool === 'mail' && options.html !== undefined
            ? { ...tool, features: [...tool.features, 'html'] }
            : tool
        ),
      },
    },
    { url: /\/api\/v1\/workbench\/mail\/folders$/, json: FOLDERS },
    {
      url: /\/api\/v1\/workbench\/mail\/counts$/,
      method: 'GET',
      json: { counts: { 'system:inbox': 2, Label_7: 1 }, truncated: false },
    },
    {
      url: /\/api\/v1\/workbench\/mail\/messages(\?.*)?$/,
      method: 'GET',
      json: { items: options.rows ?? ROWS, next_page_token: 'p2', skipped: 1 },
    },
    { url: /\/api\/v1\/workbench\/mail\/message\?/, method: 'GET', json: MESSAGE },
    {
      url: /\/api\/v1\/workbench\/mail\/conversation\?/,
      method: 'GET',
      json: options.conversation ?? { items: [], truncated: false },
    },
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
      url: /\/api\/v1\/workbench\/mail\/move$/,
      method: 'POST',
      handler: async route => {
        const body = route.request().postDataJSON() as { message_ids: string[]; to: string };
        played.moves.push(body);
        const failed = body.message_ids.includes('m2') && body.message_ids.length > 1;
        const done = body.message_ids.filter(id => !(failed && id === 'm2'));
        await route.fulfill({
          json: {
            done,
            failed: failed ? [{ id: 'm2', status: 'failed' }] : [],
            moved: done.map(id => ({ id, new_id: `${id}-moved` })),
          },
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
      url: /\/api\/v1\/workbench\/mail\/signature$/,
      handler: async route => {
        if (route.request().method() === 'PUT') {
          played.signature = (route.request().postDataJSON() as { text: string }).text;
        }
        const text = played.signature;
        await route.fulfill({ json: { text, block: text ? `\n\n-- \n${text}` : '' } });
      },
    },
    {
      url: /\/api\/v1\/workbench\/mail\/reply-recipients\?/,
      method: 'GET',
      json: {
        to: [{ name: 'Ana', address: 'ana@example.org' }],
        cc: [{ name: '', address: 'carl@example.org' }],
      },
    },
    {
      url: /\/api\/v1\/workbench\/mail\/reply$/,
      method: 'POST',
      handler: async route => {
        played.replies.push(route.request().postDataJSON() as Record<string, unknown>);
        await route.fulfill({ json: { id: 's2', thread_id: 't9' } });
      },
    },
    {
      url: /\/api\/v1\/workbench\/mail\/files$/,
      method: 'POST',
      handler: async route => {
        await route.fulfill({
          status: 201,
          json: {
            id: '11111111-1111-4111-8111-111111111111',
            filename: 'notes.txt',
            mime_type: 'text/plain',
            size: 5,
            origin: 'upload',
            expires_at: null,
          },
        });
      },
    },
    {
      url: /\/api\/v1\/workbench\/mail\/drafts$/,
      method: 'POST',
      handler: async route => {
        played.drafts.push(route.request().postDataJSON() as Record<string, unknown>);
        await route.fulfill({
          json: {
            id: 'd1',
            revision: `r${played.drafts.length}`,
            sender: null,
            to: [],
            cc: [],
            bcc: [],
            subject: '',
            body: '',
            attachments: [],
            updated_at: null,
          },
        });
      },
    },
    {
      url: /\/api\/v1\/workbench\/mail\/send$/,
      method: 'POST',
      handler: async route => {
        played.sends += 1;
        played.bodies.push(route.request().postDataJSON() as Record<string, unknown>);
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

test('the original layout opens a link in a tab of its own and stays where it is', async ({
  page,
  authenticate,
  mockApi,
}) => {
  await authenticate({ timezone: 'Europe/Paris' });
  await playTheApi(mockApi, {
    html:
      '<p>Readable original</p>' +
      '<a href="https://www.example.org/mail-link-probe" target="_self">Explicit target</a>' +
      '<a href="javascript:window.parent.postMessage(1,\'*\')" target="_top">Script link</a>' +
      '<script>window.parent.postMessage("mail-script-ran", "*")</script>',
  });
  await page
    .context()
    .route('https://www.example.org/mail-link-probe', route =>
      route.fulfill({ contentType: 'text/html', body: '<title>Opened</title>' })
    );
  await page.goto('/en/dashboard/tools/mail?id=m1');
  const original = page.frameLocator('iframe[sandbox]');
  await expect(original.getByText('Readable original')).toBeVisible();

  const tab = page.context().waitForEvent('page');
  await original.getByText('Explicit target', { exact: true }).click();
  const opened = await tab;
  await expect(opened).toHaveTitle('Opened');
  expect(await opened.evaluate(() => window.opener)).toBeNull();
  expect(await opened.evaluate(() => document.referrer)).toBe('');
  await opened.close();

  await original.getByText('Script link', { exact: true }).click();
  await expect(original.getByText('Readable original')).toBeVisible();
  expect(page.context().pages()).toHaveLength(1);
});

test('a remote image leaves only on the person’s click, and the screen offers just that', async ({
  page,
  authenticate,
  mockApi,
}) => {
  await authenticate({ timezone: 'Europe/Paris' });
  await playTheApi(mockApi, {
    html: '<p>Readable original</p><img alt="logo" src="https://www.example.org/mail-image-probe">',
  });
  const requests: string[] = [];
  await page.context().route('https://www.example.org/mail-image-probe', async route => {
    requests.push(route.request().url());
    await route.fulfill({
      contentType: 'image/gif',
      body: Buffer.from('R0lGODlhAQABAIAAAAAAAP///yH5BAEAAAAALAAAAAABAAEAAAIBRAA7', 'base64'),
    });
  });
  await page.goto('/en/dashboard/tools/mail?id=m1');
  const original = page.frameLocator('iframe[sandbox]');
  await expect(original.getByText('Readable original')).toBeVisible();
  await expect(page.getByRole('button', { name: 'Show the images' })).toBeVisible();
  await expect(page.getByText(/Remote images are/)).toHaveCount(0);
  expect(requests).toEqual([]);
  const drawnWidth = () =>
    original
      .getByRole('img', { name: 'logo' })
      .evaluate(image => (image as HTMLImageElement).naturalWidth);
  expect(await drawnWidth()).toBe(0);

  await page.getByRole('button', { name: 'Show the images' }).click();

  await expect.poll(() => requests.length).toBeGreaterThan(0);
  await expect.poll(drawnWidth).toBe(1);
  // The offer stays where it stood, greyed: the page does not jump, and it says it was taken.
  await expect(page.getByRole('button', { name: 'Show the images' })).toBeDisabled();
  await expect(page.getByText(/Remote images are/)).toHaveCount(0);
  await expect(page.locator('iframe[sandbox]')).toBeFocused();
});

/** Owner request (2026-11-05): an attachment read before it is saved, as a drive's file is. */
test('an attachment is read in a window of the page, its download beside it', async ({
  page,
  authenticate,
  mockApi,
}) => {
  await authenticate({ timezone: 'Europe/Paris' });
  await playTheApi(mockApi);
  const asked: string[] = [];
  await page.route('**/api/v1/workbench/mail/attachment/preview?*', async route => {
    asked.push(new URL(route.request().url()).searchParams.get('filename') ?? '');
    await route.fulfill({
      contentType: 'application/json',
      headers: { 'X-Preview-Truncated': 'false' },
      body: JSON.stringify({ sheets: [{ name: 'Budget', rows: [['Rent', '700']], cut: false }] }),
    });
  });

  await page.goto('/en/dashboard/tools/mail?id=m1');
  await page.getByRole('button', { name: 'Look at budget-2027.xlsx' }).click();

  const window = page.getByRole('dialog');
  await expect(window.getByRole('cell', { name: 'Rent' })).toBeVisible();
  expect(asked).toEqual(['budget-2027.xlsx']);
  expect((await new AxeBuilder({ page }).include('[role="dialog"]').analyze()).violations).toEqual(
    []
  );
});

test('a PDF attachment is read whole in the window, a phone included', async ({
  page,
  authenticate,
  mockApi,
}) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await authenticate({ timezone: 'Europe/Paris' });
  await playTheApi(mockApi);
  await page.route('**/api/v1/workbench/mail/attachment/preview?*', async route => {
    await route.fulfill({
      contentType: 'application/pdf',
      headers: { 'X-Preview-Truncated': 'false' },
      body: readFileSync(join(__dirname, '../fixtures/viewers/report.pdf')),
    });
  });

  await page.goto('/en/dashboard/tools/mail?id=m1');
  await page.getByRole('button', { name: 'Look at budget-2027.xlsx' }).click();

  const window = page.getByRole('dialog');
  await expect(window.getByText('3 pages')).toBeVisible();
  await expect(window.getByText('First page of proof')).toBeAttached();
  const sheet = await window.getByRole('group', { name: 'Page 1' }).boundingBox();
  const box = await window.boundingBox();
  expect(sheet?.width ?? 0).toBeGreaterThan(200);
  expect(sheet?.width ?? 0).toBeLessThanOrEqual(box?.width ?? 0);
});

/** Audit 2026-11-06: only the first line shares its width with the row's menu. */
test('on a phone a subject reads to the edge of its row, under the menu', async ({
  page,
  authenticate,
  mockApi,
}) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await authenticate({ timezone: 'Europe/Paris' });
  await playTheApi(mockApi);

  await page.goto('/en/dashboard/tools/mail');

  const row = page.getByRole('listitem').filter({ hasText: 'Camille Martin' }).first();
  const menu = await row
    .getByRole('button', { name: /Actions|actions/ })
    .first()
    .boundingBox();
  const subject = await row.getByText('Committee agenda for Thursday').boundingBox();
  if (menu === null || subject === null) throw new Error('not drawn');
  expect(subject.x + subject.width).toBeGreaterThan(menu.x + menu.width / 2);
  expect(subject.y).toBeGreaterThanOrEqual(menu.y + menu.height - 12);
  await expectNoOverflow(page, 'the mail list at 390px');
});

/** The mean of each colour of a picture, from 0 to 1, read on a blank page's canvas. */
async function paintOf(page: Page, shot: Buffer): Promise<[number, number, number]> {
  const reader = await page.context().newPage();
  const paint = await reader.evaluate(
    async source => {
      const bitmap = await createImageBitmap(await (await fetch(source)).blob());
      const canvas = new OffscreenCanvas(bitmap.width, bitmap.height);
      const drawing = canvas.getContext('2d');
      if (drawing === null) throw new Error('no canvas');
      drawing.drawImage(bitmap, 0, 0);
      const { data } = drawing.getImageData(0, 0, bitmap.width, bitmap.height);
      const sums = [0, 0, 0];
      for (let index = 0; index < data.length; index += 4) {
        for (const channel of [0, 1, 2]) sums[channel] += data[index + channel] ?? 0;
      }
      const pixels = data.length / 4;
      return sums.map(sum => sum / pixels / 255);
    },
    `data:image/png;base64,${shot.toString('base64')}`
  );
  await reader.close();
  return [paint[0] ?? 0, paint[1] ?? 0, paint[2] ?? 0];
}

const lightOf = ([red, green, blue]: [number, number, number]) =>
  0.2126 * red + 0.7152 * green + 0.0722 * blue;

/** A pixel of pure red, drawn large. */
const RED_PIXEL = 'data:image/gif;base64,R0lGODlhAQABAIAAAP8AAAAAACwAAAAAAQABAAACAkQBADs=';

/**
 * Owner request (2026-11-05): a mail follows the dark theme. Read on the pixels: whatever colours
 * its author wrote, the paper turns down; a picture keeps its colours; the sender's come back on
 * a click.
 */
test('a mail turns down with a dark theme, its picture keeping its colours', async ({
  page,
  authenticate,
  mockApi,
}) => {
  await page.setViewportSize({ width: 1280, height: 900 });
  await prepareTheme(page, 'dark');
  await authenticate({ timezone: 'Europe/Paris' });
  await playTheApi(mockApi, {
    html:
      '<body style="margin:0;background:#ffffff;color:#111111">' +
      '<table bgcolor="#fafafa" width="100%"><tr><td height="300">Readable original</td></tr></table>' +
      `<img alt="photo" width="160" height="160" src="${RED_PIXEL}"></body>`,
  });

  await page.goto('/en/dashboard/tools/mail?id=m1');
  const frame = page.locator('iframe[sandbox]');
  const original = page.frameLocator('iframe[sandbox]');
  await expect(original.getByText('Readable original')).toBeVisible();

  expect(lightOf(await paintOf(page, await frame.screenshot()))).toBeLessThan(0.3);
  const [red, green, blue] = await paintOf(
    page,
    await original.getByRole('img', { name: 'photo' }).screenshot()
  );
  // The two filters clip a colour at full saturation: it stays red, a little paler.
  expect(red).toBeGreaterThan(0.6);
  expect(red).toBeGreaterThan(2 * green);
  expect(red).toBeGreaterThan(2 * blue);

  await page.getByRole('button', { name: 'Show original' }).click();
  await expect(original.getByText('Readable original')).toBeVisible();
  await expect
    .poll(async () => lightOf(await paintOf(page, await frame.screenshot())))
    .toBeGreaterThan(0.7);

  await page.getByRole('button', { name: 'Follow the theme' }).click();
  await expect
    .poll(async () => lightOf(await paintOf(page, await frame.screenshot())))
    .toBeLessThan(0.3);
});

/** A large screen opens on the newest message: what follows reads the list alone. */
async function closeTheFirstMessage(page: Page): Promise<void> {
  await page.getByRole('button', { name: 'Close the message' }).click();
  await expect(page.getByRole('article')).toHaveCount(0);
}

type Box = { x: number; y: number; width: number; height: number };
const middleOf = (box: Box) => box.y + box.height / 2;

async function boxOf(target: Locator): Promise<Box> {
  const box = await target.boundingBox();
  if (box === null) throw new Error('not drawn');
  return box;
}

const rowOf = (page: Page, subject: string) =>
  page.getByRole('listitem').filter({ has: page.getByText(subject, { exact: true }) });

/**
 * Owner requests (2026-11-05): laid out in full, a row's acts start at its left, on the line of
 * its checkbox and above the sender, what the row says of itself after them.
 */
test('a row’s acts start at its left, on the line of its checkbox, above the sender', async ({
  page,
  authenticate,
  mockApi,
}) => {
  await page.setViewportSize({ width: 1280, height: 900 });
  await authenticate({ timezone: 'Europe/Paris' });
  await playTheApi(mockApi);
  await page.goto('/en/dashboard/tools/mail');
  await waitForHydration(page, 'a[data-mail-row]');
  await closeTheFirstMessage(page);

  const row = rowOf(page, 'Committee agenda for Thursday');
  const tick = await boxOf(row.getByRole('checkbox'));
  const act = await boxOf(row.getByRole('button', { name: /^Mark as read/ }));
  const link = await boxOf(row.locator('a[data-mail-row]'));

  expect(Math.abs(middleOf(act) - middleOf(tick))).toBeLessThanOrEqual(1);
  expect(act.x - (tick.x + tick.width)).toBeLessThanOrEqual(16);
  expect(act.y + act.height).toBeLessThanOrEqual(link.y + 1);
  expect((await boxOf(row.getByRole('img', { name: 'Has attachments' }))).x).toBeGreaterThan(act.x);
});

/** The list's width at every frame, until the reader has been gone for twenty of them. */
function filmOfTheListWidth(page: Page): Promise<number[]> {
  return page.evaluate(
    () =>
      new Promise<number[]>(resolve => {
        const widths: number[] = [];
        let framesWithoutTheReader = 0;
        const frame = () => {
          const list = document.querySelector('ul:has(a[data-mail-row])');
          widths.push(list?.getBoundingClientRect().width ?? 0);
          if (document.querySelector('article') === null) framesWithoutTheReader += 1;
          if (framesWithoutTheReader < 20) requestAnimationFrame(frame);
          else resolve(widths);
        };
        requestAnimationFrame(frame);
      })
  );
}

/**
 * This suite runs as a person who asked for less motion, and that person gets the final layout at
 * once. A transition of any duration, however short, paints a frame at the old value: the list at
 * no width at all, once its reader closes.
 */
test('a closing reader gives the list its room in one step', async ({
  page,
  authenticate,
  mockApi,
}) => {
  await page.setViewportSize({ width: 1280, height: 900 });
  await authenticate({ timezone: 'Europe/Paris' });
  await playTheApi(mockApi);
  await page.goto('/en/dashboard/tools/mail');
  await waitForHydration(page, 'a[data-mail-row]');
  await expect(page.getByRole('article')).toHaveCount(1);

  const film = filmOfTheListWidth(page);
  await closeTheFirstMessage(page);
  const widths = await film;

  const [before, after] = [widths[0], widths[widths.length - 1]];
  expect(after).toBeGreaterThan(before);
  expect(Math.min(...widths)).toBeGreaterThanOrEqual(before);
});

/** Owner request (2026-11-05): the unread dot stands before the sender, whatever the width. */
for (const width of [1280, 390]) {
  test(`the unread dot stands before the sender at ${width}px`, async ({
    page,
    authenticate,
    mockApi,
  }) => {
    await page.setViewportSize({ width, height: 900 });
    await authenticate({ timezone: 'Europe/Paris' });
    await playTheApi(mockApi);
    await page.goto('/en/dashboard/tools/mail');
    await waitForHydration(page, 'a[data-mail-row]');

    const unread = rowOf(page, 'Committee agenda for Thursday');
    const dot = await boxOf(unread.locator('a[data-mail-row] .bg-primary'));
    const name = await boxOf(unread.getByText('Camille Martin'));
    expect(dot.x + dot.width).toBeLessThanOrEqual(name.x);
    expect(name.x - (dot.x + dot.width)).toBeLessThanOrEqual(12);
    expect(Math.abs(middleOf(dot) - middleOf(name))).toBeLessThanOrEqual(3);

    const read = rowOf(page, 'Minutes — sprint review 22');
    await expect(read.locator('a[data-mail-row] .bg-primary')).toHaveCount(0);
    const sender = await boxOf(read.getByText('Product team'));
    const subject = await boxOf(read.getByText('Minutes — sprint review 22'));
    expect(sender.x).toBe(subject.x);
  });
}

test('in the compact density the names line up, read or not', async ({
  page,
  authenticate,
  mockApi,
}) => {
  await page.setViewportSize({ width: 1280, height: 900 });
  await page.addInitScript(() => localStorage.setItem('lia_workbench_mail_density', 'compact'));
  await authenticate({ timezone: 'Europe/Paris' });
  await playTheApi(mockApi);
  await page.goto('/en/dashboard/tools/mail');
  await waitForHydration(page, 'a[data-mail-row]');

  const unread = rowOf(page, 'Committee agenda for Thursday');
  const dot = await boxOf(unread.locator('a[data-mail-row] .bg-primary'));
  const name = await boxOf(unread.getByText('Camille Martin'));
  const other = await boxOf(rowOf(page, 'Minutes — sprint review 22').getByText('Product team'));

  expect(dot.x + dot.width).toBeLessThanOrEqual(name.x);
  expect(other.x).toBe(name.x);
});

/**
 * Owner request (2026-11-05): where a row's acts are laid out their star says it all; folded in
 * a menu, on a phone or beside the open message, the mark is the only one left to see.
 */
for (const sample of [
  { width: 1280, address: '', mark: false },
  { width: 1280, address: '?id=m2', mark: true },
  { width: 390, address: '', mark: true },
]) {
  test(`a starred row shows one star at ${sample.width}px on ${sample.address || 'the list'}`, async ({
    page,
    authenticate,
    mockApi,
  }) => {
    await page.setViewportSize({ width: sample.width, height: 900 });
    await authenticate({ timezone: 'Europe/Paris' });
    await playTheApi(mockApi);
    await page.goto(`/en/dashboard/tools/mail${sample.address}`);
    await waitForHydration(page, 'a[data-mail-row]');
    if (sample.width >= 1280 && !sample.address) await closeTheFirstMessage(page);

    const row = rowOf(page, 'Committee agenda for Thursday');
    const mark = row.getByRole('img', { name: 'Starred' });
    const act = row.getByRole('button', { name: /^Remove the star/ });
    await expect(sample.mark ? mark : act).toBeVisible();
    await expect(sample.mark ? act : mark).toBeHidden();
  });
}

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
  await closeTheFirstMessage(page);
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
  await bar.getByRole('button', { name: 'Delete' }).click();

  await expect(page.getByText('Done for 1, not for 1: those stay listed.')).toBeVisible();
  await expect(page.getByText('Committee agenda for Thursday')).toHaveCount(0);
  await expect(page.getByText('Your October statement is available')).toBeVisible();
});

test('a message archived comes back by the toast, under the id it left with', async ({
  page,
  authenticate,
  mockApi,
}) => {
  await page.setViewportSize({ width: 1280, height: 900 });
  await authenticate({ timezone: 'Europe/Paris' });
  const played = await playTheApi(mockApi);

  await page.goto('/en/dashboard/tools/mail');
  await waitForHydration(page, 'a[data-mail-row]');
  await closeTheFirstMessage(page);
  await page.getByRole('button', { name: 'Archive “Your October statement is available”' }).click();

  await expect(page.getByText('1 message archived')).toBeVisible();
  await page.getByRole('button', { name: 'Undo' }).click();

  await expect(page.getByText('1 message back')).toBeVisible();
  expect(played.moves).toEqual([
    { message_ids: ['m2'], to: 'system:archive', origin: 'system:inbox' },
    { message_ids: ['m2-moved'], to: 'system:inbox', origin: 'system:archive' },
  ]);
});

test('a row dragged to a folder lands there, and a short press still opens it', async ({
  page,
  authenticate,
  mockApi,
}) => {
  await page.setViewportSize({ width: 1280, height: 900 });
  await authenticate({ timezone: 'Europe/Paris' });
  const played = await playTheApi(mockApi);

  await page.goto('/en/dashboard/tools/mail');
  await waitForHydration(page, 'a[data-mail-row]');
  const row = page.locator('a[data-mail-row]').filter({ hasText: 'Your October statement' });
  const folder = page.locator('a[data-folder="Label_8"]');
  const from = (await row.boundingBox())!;
  const to = (await folder.boundingBox())!;

  await page.mouse.move(from.x + 40, from.y + 10);
  await page.mouse.down();
  await page.mouse.move(from.x + 20, from.y + 10, { steps: 4 });
  await page.mouse.move(to.x + 30, to.y + 10, { steps: 8 });
  await expect(page.getByText('1 message', { exact: true })).toBeVisible();
  await page.mouse.up();

  await expect(page.getByText('1 message moved')).toBeVisible();
  expect(played.moves).toEqual([{ message_ids: ['m2'], to: 'Label_8', origin: 'system:inbox' }]);
  await expect(page).not.toHaveURL(/id=/);
});

test('on a phone every act of the open message stays within reach', async ({
  page,
  authenticate,
  mockApi,
}) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await authenticate({ timezone: 'Europe/Paris' });
  await playTheApi(mockApi);

  await page.goto('/en/dashboard/tools/mail?id=m1');
  const reader = page.getByRole('article');
  await expect(reader.getByRole('button', { name: 'Ask LIA' })).toBeVisible();

  for (const button of await reader.getByRole('button').all()) {
    const box = await button.boundingBox();
    if (box) expect(box.x + box.width).toBeLessThanOrEqual(390);
  }
  await reader.getByRole('button', { name: 'More actions' }).click();
  await expect(page.getByRole('menuitem', { name: 'Archive' })).toBeVisible();
  await expect(page.getByRole('menuitem', { name: 'Move to…' })).toBeVisible();
  await expect(page.getByRole('menuitem', { name: 'Report as spam' })).toBeVisible();
});

/* AN OPEN MESSAGE'S BAR: « … », then the trash, then the question (owner, 2026-11-06). */
for (const width of [1280, 390]) {
  test(`a message's bar ends on the trash and the question at ${width}px`, async ({
    page,
    authenticate,
    mockApi,
  }) => {
    await page.setViewportSize({ width, height: 844 });
    await authenticate({ timezone: 'Europe/Paris' });
    await playTheApi(mockApi);

    await page.goto('/en/dashboard/tools/mail?id=m1');
    const reader = page.getByRole('article', { name: 'Committee agenda for Thursday' });
    await expectOnOneLine(
      reader.getByRole('button', { name: 'More actions' }),
      reader.getByRole('button', { name: 'Delete' }),
      reader.getByRole('button', { name: 'Ask LIA' })
    );
    await expect(reader.getByRole('button', { name: 'Archive' })).toHaveCount(0);
    await expect(reader.getByRole('button', { name: 'Report as spam' })).toHaveCount(0);
    await expect(reader.getByRole('button', { name: 'Move to…' })).toHaveCount(0);
    await expectInside(reader, reader.getByRole('button', { name: 'Ask LIA' }));
    await expectNoOverflow(page, `the message's bar at ${width}px`);
  });
}

/* THE MAILBOX'S OPENING: on a large screen, its newest message (owner, 2026-11-06). */
test('a large screen opens on the newest message, unread until the person opens it', async ({
  page,
  authenticate,
  mockApi,
}) => {
  await page.setViewportSize({ width: 1280, height: 900 });
  await authenticate({ timezone: 'Europe/Paris' });
  await playTheApi(mockApi);
  const marks: unknown[] = [];
  page.on('request', request => {
    if (request.url().endsWith('/workbench/mail/read-state')) marks.push(request.postDataJSON());
  });

  await page.goto('/en/dashboard/tools/mail');
  const reader = page.getByRole('article', { name: 'Committee agenda for Thursday' });
  await expect(reader.getByText('Quarter review', { exact: false })).toBeVisible();

  expect(new URL(page.url()).search).toBe('');
  await page.waitForTimeout(1500);
  expect(marks).toEqual([]);

  await page.locator('a[data-mail-row]').first().click();
  await expect.poll(() => new URL(page.url()).searchParams.get('id')).toBe('m1');
  await expect.poll(() => marks.length, { timeout: 5000 }).toBe(1);
});

test('closing the message a large screen opened leaves the list alone, for the visit', async ({
  page,
  authenticate,
  mockApi,
}) => {
  await page.setViewportSize({ width: 1600, height: 900 });
  await authenticate({ timezone: 'Europe/Paris' });
  await playTheApi(mockApi);

  await page.goto('/en/dashboard/tools/mail');
  const reader = page.getByRole('article', { name: 'Committee agenda for Thursday' });
  await expect(reader).toBeVisible();
  await reader.getByRole('button', { name: 'Close the message' }).click();

  await expect(page.getByRole('article')).toHaveCount(0);
  await expect(page.locator('a[data-mail-row]').first()).toBeFocused();
  await page.getByRole('button', { name: 'Refresh' }).click();
  await expect(page.getByRole('article')).toHaveCount(0);
});

for (const width of [1024, 390]) {
  test(`at ${width}px the mailbox opens on its list, the folders still in reach`, async ({
    page,
    authenticate,
    mockApi,
  }) => {
    await page.setViewportSize({ width, height: 844 });
    await authenticate({ timezone: 'Europe/Paris' });
    await playTheApi(mockApi);

    await page.goto('/en/dashboard/tools/mail');
    await waitForHydration(page, 'a[data-mail-row]');
    await expect(page.locator('a[data-mail-row]').first()).toBeVisible();
    await expect(page.getByRole('article')).toHaveCount(0);
  });
}

test('the pane and the pill say what the mailbox leaves unread', async ({
  page,
  authenticate,
  mockApi,
}) => {
  await page.setViewportSize({ width: 1280, height: 900 });
  await authenticate({ timezone: 'Europe/Paris' });
  await playTheApi(mockApi);

  await page.goto('/en/dashboard/tools/mail');
  await waitForHydration(page, 'a[data-mail-row]');

  await expect(page.getByRole('link', { name: 'Inbox (2 unread)' })).toBeVisible();
  await expect(page.getByRole('link', { name: 'Work (1 unread)' })).toBeVisible();
  await expect(page.getByText('2 unread messages')).toBeAttached();
  await expect(page.getByRole('img', { name: 'Has attachments' }).first()).toBeVisible();
});

test('a filter is deleted after the question says what it does', async ({
  page,
  authenticate,
  mockApi,
}) => {
  await page.setViewportSize({ width: 1280, height: 900 });
  await authenticate({ timezone: 'Europe/Paris' });
  await playTheApi(mockApi);
  let filters = [
    {
      id: 'f1',
      sender: 'news@example.org',
      recipient: null,
      subject: null,
      query: null,
      has_attachment: false,
      add_label_ids: [],
      archive: true,
      mark_read: false,
      forward: null,
    },
  ];
  await mockApi([
    {
      url: /\/api\/v1\/workbench\/mail\/vacation$/,
      json: { enabled: false, subject: '', body: '', start_date: null, end_date: null },
    },
    {
      url: /\/api\/v1\/workbench\/mail\/filters(\?.*)?$/,
      handler: async route => {
        if (route.request().method() === 'DELETE') {
          filters = [];
          await route.fulfill({ status: 204 });
          return;
        }
        await route.fulfill({ json: { filters } });
      },
    },
  ]);

  await page.goto('/en/dashboard/tools/mail');
  await waitForHydration(page, 'a[data-mail-row]');
  await page.getByRole('button', { name: 'Mailbox settings' }).click();
  await page.getByRole('tab', { name: 'Filters' }).click();
  await page.getByRole('button', { name: /^Delete the filter/ }).click();

  const question = page.getByRole('alertdialog');
  await expect(question).toContainText('news@example.org');
  await expect(question).toContainText('Archives');
  await question.getByRole('button', { name: 'Delete' }).click();

  await expect(page.getByText('Filter deleted')).toBeVisible();
  await expect(page.getByRole('button', { name: /^Delete the filter/ })).toHaveCount(0);
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
    .getByRole('button', { name: 'New email' })
    .click();
  const dialog = page.getByRole('dialog', { name: 'New email' });
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

test('« Send » holds the message a moment, and « Undo » gives it back unsent', async ({
  page,
  authenticate,
  mockApi,
}) => {
  await page.setViewportSize({ width: 1280, height: 900 });
  await authenticate({ timezone: 'Europe/Paris' });
  const played = await playTheApi(mockApi, { undoSeconds: 5 });

  await page.goto('/en/dashboard/tools/mail');
  await waitForHydration(page, 'a[data-mail-row]');
  await page
    .getByRole('navigation', { name: 'Folders' })
    .getByRole('button', { name: 'New email' })
    .click();
  const dialog = page.getByRole('dialog', { name: 'New email' });
  await dialog.getByRole('combobox', { name: 'To' }).fill('ana@example.org');
  await dialog.getByRole('textbox', { name: 'Message' }).fill('See you there.');
  await dialog.getByRole('button', { name: 'Send' }).click();

  const undo = page.getByRole('button', { name: 'Undo' });
  await expect(undo).toBeFocused();
  await expect(dialog).toBeHidden();
  await undo.click();

  await expect(dialog.getByRole('textbox', { name: 'Message' })).toHaveValue('See you there.');
  await expect(dialog.getByRole('textbox', { name: 'Message' })).toBeFocused();
  expect(played.sends).toBe(0);
});

/** Opens the composer on a new message, the mail screen read. */
async function newMessage(page: Page, width = 1280) {
  await page.goto('/en/dashboard/tools/mail');
  await waitForHydration(page, 'a[data-mail-row]');
  const pane = width < 1024 ? page : page.getByRole('navigation', { name: 'Folders' });
  await pane.getByRole('button', { name: 'New email' }).first().click();
  return page.getByRole('dialog', { name: 'New email' });
}

test('words marked in the browser leave with their marks, and the dialog stays clean', async ({
  page,
  authenticate,
  mockApi,
}) => {
  await page.setViewportSize({ width: 1280, height: 900 });
  await authenticate({ timezone: 'Europe/Paris' });
  const played = await playTheApi(mockApi);

  const dialog = await newMessage(page);
  await dialog.getByRole('combobox', { name: 'To' }).fill('ana@example.org');
  await dialog.getByRole('button', { name: 'Formatting' }).click();
  const words = dialog.getByRole('textbox', { name: 'Message' });
  await words.click();
  await page.keyboard.type('Important');
  await page.keyboard.press('ControlOrMeta+a');
  await dialog.getByRole('button', { name: 'Bold' }).click();
  await expect(words.locator('b, strong')).toHaveText('Important');

  const scan = await new AxeBuilder({ page }).include('[role="dialog"]').analyze();
  expect(scan.violations).toEqual([]);

  await dialog.getByRole('button', { name: 'Send' }).click();

  await expect(dialog).toHaveCount(0);
  expect(String(played.bodies[0]?.html)).toMatch(/<(b|strong)>Important<\/(b|strong)>/);
  expect(played.bodies[0]?.body).toBe('Important');
});

test('what is pasted arrives as words, whatever the page it came from', async ({
  page,
  authenticate,
  mockApi,
}) => {
  await page.setViewportSize({ width: 1280, height: 900 });
  await authenticate({ timezone: 'Europe/Paris' });
  await playTheApi(mockApi);

  const dialog = await newMessage(page);
  await dialog.getByRole('button', { name: 'Formatting' }).click();
  const words = dialog.getByRole('textbox', { name: 'Message' });
  await words.click();
  await words.evaluate(field => {
    const data = new DataTransfer();
    data.setData('text/plain', 'plain words');
    data.setData('text/html', '<img src=x onerror=alert(1)><b>marked</b>');
    field.dispatchEvent(
      new ClipboardEvent('paste', { clipboardData: data, bubbles: true, cancelable: true })
    );
  });

  await expect(words).toHaveText('plain words');
  await expect(words.locator('img, b')).toHaveCount(0);
});

test('a link is made of the selection, and an address nobody should follow is refused', async ({
  page,
  authenticate,
  mockApi,
}) => {
  await page.setViewportSize({ width: 1280, height: 900 });
  await authenticate({ timezone: 'Europe/Paris' });
  await playTheApi(mockApi);

  const dialog = await newMessage(page);
  await dialog.getByRole('button', { name: 'Formatting' }).click();
  const words = dialog.getByRole('textbox', { name: 'Message' });
  await words.click();
  await page.keyboard.type('site');
  await page.keyboard.press('ControlOrMeta+a');
  await dialog.getByRole('button', { name: 'Link' }).click();
  const address = page.getByRole('textbox', { name: 'Address' });

  await address.fill('javascript:alert(1)');
  await page.getByRole('button', { name: 'Add', exact: true }).click();
  await expect(page.getByText('This address cannot be a link')).toBeVisible();

  await address.fill('example.org');
  await page.getByRole('button', { name: 'Add', exact: true }).click();

  await expect(words.getByRole('link', { name: 'site' })).toHaveAttribute(
    'href',
    'https://example.org'
  );
});

test('a reply shows whom it reaches and leaves to whom the person left', async ({
  page,
  authenticate,
  mockApi,
}) => {
  await page.setViewportSize({ width: 1280, height: 900 });
  await authenticate({ timezone: 'Europe/Paris' });
  const played = await playTheApi(mockApi);

  await page.goto('/en/dashboard/tools/mail');
  await waitForHydration(page, 'a[data-mail-row]');
  await page.locator('a[data-mail-row]').first().click();
  await page.getByRole('button', { name: 'Reply', exact: true }).first().click();
  const dialog = page.getByRole('dialog', { name: 'Reply' });
  const copies = dialog.getByRole('combobox', { name: 'Cc' });
  await expect(dialog.getByRole('combobox', { name: 'To' })).toHaveValue('ana@example.org');
  await expect(copies).toHaveValue('carl@example.org');

  await copies.fill('');
  await dialog.getByRole('textbox', { name: 'Message' }).fill('Thanks');
  await dialog.getByRole('button', { name: 'Send' }).click();

  await expect(dialog).toHaveCount(0);
  expect(played.replies[0]).toMatchObject({ to: ['ana@example.org'], cc: [], body: 'Thanks' });
});

/** Owner question (2026-11-06): an answer can be kept for later, as a new message can. */
test('a reply is kept as a draft of its thread, and the composer closes on it', async ({
  page,
  authenticate,
  mockApi,
}) => {
  await page.setViewportSize({ width: 1280, height: 900 });
  await authenticate({ timezone: 'Europe/Paris' });
  const played = await playTheApi(mockApi);

  await page.goto('/en/dashboard/tools/mail');
  await waitForHydration(page, 'a[data-mail-row]');
  await page.locator('a[data-mail-row]').first().click();
  await page.getByRole('button', { name: 'Reply', exact: true }).first().click();
  const dialog = page.getByRole('dialog', { name: 'Reply' });
  await expect(dialog.getByRole('combobox', { name: 'To' })).toHaveValue('ana@example.org');
  await dialog.getByRole('textbox', { name: 'Message' }).fill('Later');
  await dialog.getByRole('button', { name: 'Draft' }).click();

  await expect(dialog).toHaveCount(0);
  await expect(page.getByText('Draft saved')).toBeVisible();
  expect(played.drafts).toHaveLength(1);
  expect(played.drafts[0]).toMatchObject({
    origin: { kind: 'reply' },
    body: 'Later',
    to: ['ana@example.org'],
    cc: ['carl@example.org'],
  });
  expect(played.replies).toHaveLength(0);
});

test('a forward asks whom it goes to before it is kept', async ({
  page,
  authenticate,
  mockApi,
}) => {
  await page.setViewportSize({ width: 1280, height: 900 });
  await authenticate({ timezone: 'Europe/Paris' });
  const played = await playTheApi(mockApi);

  await page.goto('/en/dashboard/tools/mail');
  await waitForHydration(page, 'a[data-mail-row]');
  await page.locator('a[data-mail-row]').first().click();
  await page.getByRole('button', { name: 'Forward' }).first().click();
  const dialog = page.getByRole('dialog', { name: 'Forward' });
  await dialog.getByRole('button', { name: 'Draft' }).click();

  await expect(dialog.getByRole('alert')).toBeVisible();
  expect(played.drafts).toHaveLength(0);
  await dialog.getByRole('combobox', { name: 'To' }).fill('ana@example.org');
  await dialog.getByRole('button', { name: 'Draft' }).click();

  await expect(dialog).toHaveCount(0);
  expect(played.drafts[0]).toMatchObject({ origin: { kind: 'forward' }, to: ['ana@example.org'] });
});

/** Owner requests (2026-11-06): one column, its words at one edge, LIA at the other. */
for (const width of [390, 1280]) {
  test(`a new email lines its fields up at ${width}px`, async ({ page, authenticate, mockApi }) => {
    await page.setViewportSize({ width, height: 900 });
    await authenticate({ timezone: 'Europe/Paris' });
    await playTheApi(mockApi, { assists: true });

    const dialog = await newMessage(page, width);
    const copies = dialog.getByRole('button', { name: 'Cc / Bcc' });
    const toLabel = dialog.getByText('To', { exact: true });
    const toBox = await toLabel.boundingBox();
    expect(Math.abs((await wordStartOf(copies)) - (toBox?.x ?? 0))).toBeLessThanOrEqual(1);

    const subject = dialog.getByRole('textbox', { name: 'Subject' });
    const body = dialog.getByRole('textbox', { name: 'Message' });
    const writes = dialog.getByRole('button', { name: 'Write with LIA' });
    await expect(writes).toHaveCount(2);
    await expectSameEnd(writes.first().locator('svg'), subject);
    await expectSameEnd(writes.last().locator('svg'), body);

    const send = dialog.getByRole('button', { name: 'Send' });
    const draft = dialog.getByRole('button', { name: 'Draft' });
    const cancel = dialog.getByRole('button', { name: 'Cancel' });
    if (width === 390) await expectStackedWhole(send, draft, cancel);
    else await expectOnOneLine(cancel, draft, send);
    await expectNoOverflow(page, `the composer at ${width}px`);
  });
}

/** Owner request (2026-11-06): the menu names the acts; its trigger has named the message. */
test('a row’s menu on a phone says what it does, not which message again', async ({
  page,
  authenticate,
  mockApi,
}) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await authenticate({ timezone: 'Europe/Paris' });
  await playTheApi(mockApi);

  await page.goto('/en/dashboard/tools/mail');
  await waitForHydration(page, 'a[data-mail-row]');
  await page.getByRole('button', { name: 'Actions: Committee agenda for Thursday' }).click();

  const lines = await page.getByRole('menuitem').allTextContents();
  expect(lines).toContain('Delete');
  expect(lines.filter(line => line.includes('Committee agenda'))).toEqual([]);
});

test.describe('on a touch screen', () => {
  test.use({ hasTouch: true, isMobile: true, viewport: { width: 390, height: 844 } });
  test.skip(({ browserName }) => browserName === 'firefox', 'no mobile emulation');

  /** Owner report (2026-11-06): iOS zoomed into a small field and stayed there. */
  test('no field of a message is one iOS would zoom into, plain or formatted', async ({
    page,
    authenticate,
    mockApi,
  }) => {
    await authenticate({ timezone: 'Europe/Paris' });
    await playTheApi(mockApi);

    await page.goto('/en/dashboard/tools/mail');
    await waitForHydration(page, 'a[data-mail-row]');
    await expectNoZoomOnFocus(page);
    await page.getByRole('button', { name: 'New email' }).first().click();
    const dialog = page.getByRole('dialog', { name: 'New email' });
    await dialog.getByRole('button', { name: 'Cc / Bcc' }).click();
    await expectNoZoomOnFocus(page);
    await dialog.getByRole('button', { name: 'Formatting' }).click();
    await expect(dialog.getByRole('textbox', { name: 'Message' })).toHaveAttribute(
      'contenteditable',
      'true'
    );
    await expectNoZoomOnFocus(page);
  });
});

test('a file of the device leaves with the message, and nothing leaves before it arrives', async ({
  page,
  authenticate,
  mockApi,
}) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await authenticate({ timezone: 'Europe/Paris' });
  const played = await playTheApi(mockApi);

  await page.goto('/en/dashboard/tools/mail');
  await waitForHydration(page, 'a[data-mail-row]');
  await page.getByRole('button', { name: 'New email' }).first().click();
  const dialog = page.getByRole('dialog', { name: 'New email' });
  await dialog.getByRole('combobox', { name: 'To' }).fill('ana@example.org');
  await dialog.getByLabel('From this device').setInputFiles({
    name: 'notes.txt',
    mimeType: 'text/plain',
    buffer: Buffer.from('hello'),
  });

  await expect(dialog.getByText('notes.txt')).toBeVisible();
  await dialog.getByRole('button', { name: 'Send' }).click();

  await expect(dialog).toHaveCount(0);
  expect(played.bodies[0]?.attachment_ids).toEqual(['11111111-1111-4111-8111-111111111111']);
});

test('a quiet composer saves by itself and says so, and sends that draft', async ({
  page,
  authenticate,
  mockApi,
}) => {
  await page.setViewportSize({ width: 1280, height: 900 });
  await authenticate({ timezone: 'Europe/Paris' });
  const played = await playTheApi(mockApi, { autosaveSeconds: 1 });

  const dialog = await newMessage(page);
  await dialog.getByRole('textbox', { name: 'Message' }).fill('Later');

  await expect(dialog.getByText('Saved in your drafts')).toBeVisible();
  expect(played.drafts).toHaveLength(1);
  expect(played.drafts[0]).toMatchObject({ body: 'Later' });
});

test('a signature written in the settings closes the next message', async ({
  page,
  authenticate,
  mockApi,
}) => {
  await page.setViewportSize({ width: 1280, height: 900 });
  await authenticate({ timezone: 'Europe/Paris' });
  await playTheApi(mockApi);

  await page.goto('/en/dashboard/tools/mail');
  await waitForHydration(page, 'a[data-mail-row]');
  await page.getByRole('button', { name: 'Mailbox settings' }).click();
  await page.getByRole('tab', { name: 'Signature' }).click();
  await page.getByRole('textbox', { name: 'Your signature' }).fill('Ana Lima');
  await page.getByRole('button', { name: 'Save' }).click();
  await expect(page.locator('[data-sonner-toast]').getByText('Signature saved')).toBeVisible();
  await page.keyboard.press('Escape');

  await page
    .getByRole('navigation', { name: 'Folders' })
    .getByRole('button', { name: 'New email' })
    .click();

  await expect(
    page.getByRole('dialog', { name: 'New email' }).getByRole('textbox', { name: 'Message' })
  ).toHaveValue('\n\n-- \nAna Lima');
});

test('the composer leaves the mail usable behind it', async ({ page, authenticate, mockApi }) => {
  await page.setViewportSize({ width: 1600, height: 900 });
  await authenticate({ timezone: 'Europe/Paris' });
  await playTheApi(mockApi);

  await page.goto('/en/dashboard/tools/mail');
  await waitForHydration(page, 'a[data-mail-row]');
  await page
    .getByRole('navigation', { name: 'Folders' })
    .getByRole('button', { name: 'New email' })
    .click();
  await expect(page.getByRole('dialog', { name: 'New email' })).toBeVisible();

  await page.locator('a[data-mail-row]').first().click();

  await expect(page).toHaveURL(/id=/);
  await expect(page.getByRole('dialog', { name: 'New email' })).toBeVisible();
  const scan = await new AxeBuilder({ page }).include('main').analyze();
  expect(scan.violations).toEqual([]);
});

test('on a phone the first message comes in the first half of the screen', async ({
  page,
  authenticate,
  mockApi,
}) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await authenticate({ timezone: 'Europe/Paris' });
  await playTheApi(mockApi);

  await page.goto('/en/dashboard/tools/mail');
  await waitForHydration(page, 'a[data-mail-row]');

  const box = await page.locator('a[data-mail-row]').first().boundingBox();
  expect(box?.y ?? Number.POSITIVE_INFINITY).toBeLessThan(330);
  await expectNoOverflow(page, 'mail list at 390px');
});

test('an image the message carries is drawn in its frame, with no click and nothing asked', async ({
  page,
  authenticate,
  mockApi,
}) => {
  await page.setViewportSize({ width: 1600, height: 900 });
  await authenticate({ timezone: 'Europe/Paris' });
  await playTheApi(mockApi, { html: '<p>Hello</p><img src="cid:logo@x" alt="logo">' });
  await mockApi([
    {
      url: /\/api\/v1\/workbench\/mail\/message\/images/,
      json: {
        images: [
          {
            cid: 'logo@x',
            data_url:
              'data:image/gif;base64,R0lGODlhAQABAIAAAAAAAP///yH5BAEAAAAALAAAAAABAAEAAAIBRAA7',
          },
        ],
        skipped: 0,
      },
    },
  ]);

  await page.goto('/en/dashboard/tools/mail');
  await waitForHydration(page, 'a[data-mail-row]');
  await page.locator('a[data-mail-row]').first().click();

  const frame = page.frameLocator('iframe[title]');
  await expect
    .poll(() =>
      frame
        .getByRole('img', { name: 'logo' })
        .evaluate(image => (image as HTMLImageElement).naturalWidth)
    )
    .toBe(1);
  await expect(page.getByText(/Remote images are hidden/)).toHaveCount(0);
});

test('one click leaves a list after a question, by the message alone', async ({
  page,
  authenticate,
  mockApi,
}) => {
  await page.setViewportSize({ width: 1600, height: 900 });
  await authenticate({ timezone: 'Europe/Paris' });
  await playTheApi(mockApi);
  const posts: unknown[] = [];
  await mockApi([
    {
      url: /\/api\/v1\/workbench\/mail\/message\/unsubscribe/,
      json: { web_url: 'https://example.org/leave', mail_to: null, one_click: true },
    },
    {
      url: /\/api\/v1\/workbench\/mail\/unsubscribe$/,
      method: 'POST',
      handler: async route => {
        posts.push(route.request().postDataJSON());
        await route.fulfill({ status: 204, body: '' });
      },
    },
  ]);

  await page.goto('/en/dashboard/tools/mail');
  await waitForHydration(page, 'a[data-mail-row]');
  await page.locator('a[data-mail-row]').first().click();
  await page.getByRole('button', { name: 'Unsubscribe' }).click();
  await page.getByRole('alertdialog').getByRole('button', { name: 'Unsubscribe' }).click();

  await expect(page.getByText('Unsubscribe request sent')).toBeVisible();
  expect(posts).toHaveLength(1);
  expect(Object.keys(posts[0] as object)).toEqual(['message_id']);
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
  await page.getByRole('button', { name: 'New email' }).first().click();
  const dialog = page.getByRole('dialog', { name: 'New email' });
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

test('a conversation is walked from above the message, the focus staying on its link', async ({
  page,
  authenticate,
  mockApi,
}) => {
  await page.setViewportSize({ width: 1600, height: 900 });
  await authenticate({ timezone: 'Europe/Paris' });
  await playTheApi(mockApi, { conversation: { items: [ROWS[3], ROWS[0]], truncated: false } });

  await page.goto('/en/dashboard/tools/mail');
  await waitForHydration(page, 'a[data-mail-row]');
  await page.locator('a[data-mail-row]').first().click();

  await page.getByRole('button', { name: '2 messages in this conversation' }).click();
  const walked = page.getByRole('list', { name: 'Messages of this conversation' });
  await expect(walked.getByRole('link', { name: /Camille Martin/ })).toHaveAttribute(
    'aria-current',
    'true'
  );
  const scan = await new AxeBuilder({ page }).include('main').analyze();
  expect(scan.violations).toEqual([]);

  const older = walked.getByRole('link', { name: /Theo Lambert/ });
  await older.focus();
  await page.keyboard.press('Enter');

  await expect(page).toHaveURL(/id=m4/);
  await expect(older).toHaveAttribute('aria-current', 'true');
  await expect(older).toBeFocused();
});

test('a phone keeps a long conversation inside its width', async ({
  page,
  authenticate,
  mockApi,
}) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await authenticate({ timezone: 'Europe/Paris' });
  await playTheApi(mockApi, { conversation: { items: ROWS, truncated: true } });

  await page.goto('/en/dashboard/tools/mail');
  await waitForHydration(page, 'a[data-mail-row]');
  await page.locator('a[data-mail-row]').first().click();
  await page.getByRole('button', { name: 'The latest 4 messages of this conversation' }).click();

  await expect(page.getByRole('list', { name: 'Messages of this conversation' })).toBeVisible();
  await expectNoOverflow(page, 'conversation at 390px');
});

test('a list by conversation draws one line, acts on all of it and is remembered', async ({
  page,
  authenticate,
  mockApi,
}) => {
  await page.setViewportSize({ width: 1600, height: 900 });
  await authenticate({ timezone: 'Europe/Paris' });
  const played = await playTheApi(mockApi, {
    rows: [ROWS[0], ROWS[1], { ...ROWS[3], thread_id: 'm1' }],
  });

  await page.goto('/en/dashboard/tools/mail');
  await waitForHydration(page, 'a[data-mail-row]');
  await expect(page.locator('a[data-mail-row]')).toHaveCount(3);

  await page.getByRole('button', { name: 'Group by conversation' }).click();

  await expect(page.locator('a[data-mail-row]')).toHaveCount(2);
  await expect(page.getByRole('img', { name: 'Several messages of a conversation' })).toBeVisible();
  const scan = await new AxeBuilder({ page }).include('main').analyze();
  expect(scan.violations).toEqual([]);

  await page.reload();
  await waitForHydration(page, 'a[data-mail-row]');
  await expect(page.locator('a[data-mail-row]')).toHaveCount(2);

  await page.getByRole('checkbox', { name: /Committee agenda/ }).click();
  await page
    .getByRole('region', { name: 'Selected messages' })
    .getByRole('button', { name: 'Delete' })
    .click();

  await expect.poll(() => played.moves.at(-1)?.message_ids).toEqual(['m1', 'm4']);
});

test('a line dragged to a folder carries every message loaded under it', async ({
  page,
  authenticate,
  mockApi,
}) => {
  await page.setViewportSize({ width: 1280, height: 900 });
  await authenticate({ timezone: 'Europe/Paris' });
  const played = await playTheApi(mockApi, {
    rows: [ROWS[0], ROWS[1], { ...ROWS[3], thread_id: 'm1' }],
  });

  await page.goto('/en/dashboard/tools/mail');
  await waitForHydration(page, 'a[data-mail-row]');
  await page.getByRole('button', { name: 'Group by conversation' }).click();
  await expect(page.locator('a[data-mail-row]')).toHaveCount(2);
  const row = page.locator('a[data-mail-row]').filter({ hasText: 'Committee agenda' });
  const folder = page.locator('a[data-folder="Label_8"]');
  const from = (await row.boundingBox())!;
  const to = (await folder.boundingBox())!;

  await page.mouse.move(from.x + 40, from.y + 10);
  await page.mouse.down();
  await page.mouse.move(from.x + 20, from.y + 10, { steps: 4 });
  await page.mouse.move(to.x + 30, to.y + 10, { steps: 8 });
  await expect(page.getByText('2 messages', { exact: true })).toBeVisible();
  await page.mouse.up();

  await expect.poll(() => played.moves.at(-1)?.message_ids).toEqual(['m1', 'm4']);
});

test('Escape gives the focus back to the line, whichever of its messages was open', async ({
  page,
  authenticate,
  mockApi,
}) => {
  await page.setViewportSize({ width: 1600, height: 900 });
  await authenticate({ timezone: 'Europe/Paris' });
  await playTheApi(mockApi, {
    rows: [ROWS[0], { ...ROWS[3], thread_id: 'm1' }],
    conversation: { items: [ROWS[3], ROWS[0]], truncated: false },
  });

  await page.goto('/en/dashboard/tools/mail');
  await waitForHydration(page, 'a[data-mail-row]');
  await page.getByRole('button', { name: 'Group by conversation' }).click();
  await expect(page.locator('a[data-mail-row]')).toHaveCount(1);
  const line = page.locator('a[data-mail-row]');
  await line.click();
  await page.getByRole('button', { name: '2 messages in this conversation' }).click();
  await page
    .getByRole('list', { name: 'Messages of this conversation' })
    .getByRole('link', { name: /Theo Lambert/ })
    .click();
  await expect(page).toHaveURL(/id=m4/);

  await page.keyboard.press('Escape');

  await expect(page).not.toHaveURL(/id=/);
  await expect(line).toBeFocused();
});

/** Owner request (2026-11-05): the list's toggles say their state to the eye, not to a reader alone. */
test('the toggles of the list show whether they are on', async ({
  page,
  authenticate,
  mockApi,
}) => {
  await page.setViewportSize({ width: 1280, height: 900 });
  await authenticate({ timezone: 'Europe/Paris' });
  await playTheApi(mockApi);
  await page.goto('/en/dashboard/tools/mail');
  await waitForHydration(page, 'a[data-mail-row]');

  for (const name of ['Group by conversation', 'Compact list']) {
    const toggle = page.getByRole('button', { name });
    const painted = () => toggle.evaluate(node => getComputedStyle(node).backgroundColor);
    await page.mouse.move(0, 0);
    const off = await painted();

    await toggle.click();
    await expect(toggle).toHaveAttribute('aria-pressed', 'true');
    await page.mouse.move(0, 0);

    await expect.poll(painted).not.toBe(off);
  }
});

test('a phone offers the grouping without losing its width', async ({
  page,
  authenticate,
  mockApi,
}) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await authenticate({ timezone: 'Europe/Paris' });
  await playTheApi(mockApi, { rows: [ROWS[0], { ...ROWS[3], thread_id: 'm1' }] });

  await page.goto('/en/dashboard/tools/mail');
  await waitForHydration(page, 'a[data-mail-row]');
  await page.getByRole('button', { name: 'Group by conversation' }).click();

  await expect(page.locator('a[data-mail-row]')).toHaveCount(1);
  await expectNoOverflow(page, 'list by conversation at 390px');
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

/* PHONE LINES: the owner's remarks of 2026-11-06. */
const LONG_LABEL = 'Clients and suppliers of the second half of the year, by region';

for (const width of [390, 360]) {
  test(`a phone reads the mail's header and its folders line by line at ${width}px`, async ({
    page,
    authenticate,
    mockApi,
  }) => {
    await page.setViewportSize({ width, height: 844 });
    await authenticate({ timezone: 'Europe/Paris' });
    await playTheApi(mockApi);
    await mockApi([
      {
        url: /\/api\/v1\/workbench\/mail\/folders$/,
        json: {
          folders: [
            ...FOLDERS.folders,
            { id: 'Label_9', kind: 'user', role: null, name: LONG_LABEL },
          ],
        },
      },
    ]);

    await page.goto('/en/dashboard/tools/mail');
    await waitForHydration(page, 'a[data-mail-row]');
    const tool = page.getByRole('region', { name: 'Mail' });
    const search = page.getByRole('button', { name: 'Search across your tools' });
    const refresh = page.getByRole('button', { name: 'Refresh' });
    const grouping = page.getByRole('button', { name: 'Group by conversation' });
    const select = page.getByRole('button', { name: 'Select', exact: true });
    const write = page.getByRole('button', { name: 'New email' }).first();
    await expect(write).toHaveText('New email');
    await expectOnOneLine(search, refresh, grouping, select, write);
    await expectSameStart(search, tool);
    await expectSameEnd(write, tool);
    for (const square of [search, refresh, grouping, select]) {
      await expect(square).toHaveCSS('width', '40px');
      await expect(square).toHaveCSS('height', '40px');
      await expect(square).toHaveCSS('border-top-width', '2px');
    }
    // On, the toggle says so to the eye: its ground is no longer the field's.
    const off = await select.evaluate(element => getComputedStyle(element).backgroundColor);
    await select.click();
    await expect(select).toHaveAttribute('aria-pressed', 'true');
    // Away from it: a pointer resting there would answer for the toggle.
    await page.mouse.move(0, 0);
    await expect
      .poll(() => select.evaluate(e => getComputedStyle(e).backgroundColor))
      .not.toBe(off);

    const list = page.getByRole('combobox', { name: 'Folder' });
    // An open list hides the page from the tree: its trigger is measured before.
    const trigger = await list.boundingBox();
    await list.click();
    const options = page.getByRole('listbox');
    await expect(options).toBeVisible();
    const opened = await options.boundingBox();
    expect(
      Math.abs((opened?.width ?? 0) - (trigger?.width ?? 0)),
      'as wide as the pane'
    ).toBeLessThanOrEqual(1);
    const long = options.getByRole('option', { name: LONG_LABEL });
    await long.scrollIntoViewIfNeeded();
    await expect(long.getByText(LONG_LABEL).first()).toBeVisible();
    expect(
      await long.evaluate(option => option.scrollWidth <= option.clientWidth),
      'a long label breaks on its lines and reads whole'
    ).toBe(true);
    await options.getByRole('option', { name: /^Sent/ }).click();
    await expect(page).toHaveURL(/folder=/);
    await expectNoOverflow(page, `the folders at ${width}px`);
  });

  test(`a phone reads a message line by line at ${width}px`, async ({
    page,
    authenticate,
    mockApi,
  }) => {
    await page.setViewportSize({ width, height: 844 });
    await prepareTheme(page, 'dark');
    await authenticate({ timezone: 'Europe/Paris' });
    await playTheApi(mockApi, {
      html: '<p>Readable original</p><img alt="far" src="https://images.example.org/p.png">',
    });

    await page.goto('/en/dashboard/tools/mail?id=m1');
    const reader = page.getByRole('article', { name: 'Committee agenda for Thursday' });
    await expect(page.frameLocator('iframe[sandbox]').getByText('Readable original')).toBeVisible();
    const answers = reader.getByRole('group', { name: 'Answer the message' }).first();
    const text = reader.getByRole('button', { name: 'Show the text' });
    const images = reader.getByRole('button', { name: 'Show the images' });
    const original = reader.getByRole('button', { name: 'Show original' });
    await expectOnOneLine(
      answers.getByRole('button', { name: 'Reply', exact: true }),
      answers.getByRole('button', { name: 'Reply all' }),
      answers.getByRole('button', { name: 'Forward' })
    );
    await expectOnOneLine(text, images, original);
    const frame = page.locator('iframe[sandbox]');
    await expectSameStart(text, frame);
    await expectSameCentre(images, frame);
    await expectSameEnd(original, frame);
    await expectUnder(answers, text);
    // Owner request (2026-11-06): where the page ends, one answer per line, the whole width.
    const ending = reader.getByRole('group', { name: 'Answer the message' }).last();
    await expectStackedWhole(
      ending.getByRole('button', { name: 'Reply', exact: true }),
      ending.getByRole('button', { name: 'Reply all' }),
      ending.getByRole('button', { name: 'Forward' })
    );
    await expect(reader.getByRole('navigation', { name: 'Answer the message' })).toBeHidden();
    await expectInside(reader, reader.getByRole('button', { name: 'More actions' }));
    await expectNoOverflow(page, `the message at ${width}px`);
  });
}

test('the phone’s list of folders answers the keyboard and gives the focus back', async ({
  page,
  authenticate,
  mockApi,
}) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await authenticate({ timezone: 'Europe/Paris' });
  await playTheApi(mockApi);

  await page.goto('/en/dashboard/tools/mail');
  await waitForHydration(page, 'a[data-mail-row]');
  const list = page.getByRole('combobox', { name: 'Folder' });
  await list.focus();
  await page.keyboard.press('Enter');
  await expect(page.getByRole('option', { name: /^Inbox/ })).toBeFocused();
  await page.keyboard.press('ArrowDown');
  await expect(page.getByRole('option', { name: 'Starred' })).toBeFocused();
  await page.keyboard.press('Enter');

  await expect(page).toHaveURL(/folder=system%3Astarred/);
  await expect(list).toBeFocused();
  await expect(list).toHaveText(/Starred/);
});

test('on a computer the views of a message stand together in the middle', async ({
  page,
  authenticate,
  mockApi,
}) => {
  await page.setViewportSize({ width: 1440, height: 900 });
  await prepareTheme(page, 'dark');
  await authenticate({ timezone: 'Europe/Paris' });
  await playTheApi(mockApi, {
    html: '<p>Readable original</p><img alt="far" src="https://images.example.org/p.png">',
  });

  await page.goto('/en/dashboard/tools/mail?id=m1');
  const reader = page.getByRole('article', { name: 'Committee agenda for Thursday' });
  await expect(page.frameLocator('iframe[sandbox]').getByText('Readable original')).toBeVisible();
  const text = reader.getByRole('button', { name: 'Show the text' });
  const images = reader.getByRole('button', { name: 'Show the images' });
  const original = reader.getByRole('button', { name: 'Show original' });

  await expectOnOneLine(text, images, original);
  await expectLinesCentredIn(page.locator('iframe[sandbox]'), text, images, original);
});

test('from `lg` a message keeps its answers in one place', async ({
  page,
  authenticate,
  mockApi,
}) => {
  await page.setViewportSize({ width: 1280, height: 900 });
  await authenticate({ timezone: 'Europe/Paris' });
  await playTheApi(mockApi);

  await page.goto('/en/dashboard/tools/mail?id=m1');
  const reader = page.getByRole('article', { name: 'Committee agenda for Thursday' });
  await expect(reader.getByRole('navigation', { name: 'Answer the message' })).toBeVisible();
  await expect(reader.getByRole('group', { name: 'Answer the message' })).toBeHidden();
});
