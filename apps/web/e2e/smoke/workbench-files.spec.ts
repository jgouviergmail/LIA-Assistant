/**
 * The « Tools » files screen, hermetic (ADR-369, Task 8.2).
 *
 * The API is played by the spec: one ready Drive, a folder holding a folder, a
 * shortcut, a Google document and a file past the ceiling. Proven at 1280 and
 * 390 px, in light, dark and OLED: no horizontal scroll, axe clean on the
 * screen; a folder opens in the list with its breadcrumb; a Google document
 * downloads once per format through the API, in a tab that cannot reach back;
 * a file past the ceiling is said, never offered; the keyboard opens a file and
 * gets its row back when it closes. Organising it runs on a phone first: a file
 * moved through a walk of the folders, a file really chosen and sent, a view, the
 * trash emptied after a question, a person given access, each dialog held within
 * the screen.
 */
import { readFileSync } from 'node:fs';
import { join } from 'node:path';

import AxeBuilder from '@axe-core/playwright';
import type { Page } from '@playwright/test';

import { test, expect, waitForHydration } from '../fixtures';
import type { MockRoute } from '../fixtures/api-mock';
import { appConfig } from '../fixtures/dashboard-shell';
import { expectNoOverflow, prepareTheme } from './overflow-report';

const CEILING = 26214400;

const RAIL = {
  tools: ['mail', 'calendar', 'tasks', 'contacts', 'files', 'lights'].map(tool =>
    tool === 'files'
      ? {
          tool,
          state: 'ready',
          provider: 'google_drive',
          features: ['export', 'file_views'],
          bounds: { file_name_max_chars: 255 },
        }
      : { tool, state: 'not_connected', provider: null, features: [], bounds: {} }
  ),
  limits: {
    page_size: 25,
    bulk_max_items: 50,
    download_max_bytes: CEILING,
    upload_max_bytes: CEILING,
    calendar_window_max_events: 500,
    send_undo_seconds: 0,
    draft_autosave_seconds: 0,
    search_max_chars: 500,
  },
};

function item(id: string, name: string, extra: Record<string, unknown> = {}) {
  return {
    id,
    name,
    kind: 'file',
    mime_type: 'application/pdf',
    modified_at: '2026-10-30T09:15:00Z',
    size: 48213,
    web_url: `https://drive.google.com/file/d/${id}/view`,
    target_id: null,
    target_kind: null,
    formats: [],
    downloadable: true,
    starred: false,
    ...extra,
  };
}

const FOLDER = {
  kind: 'folder',
  mime_type: 'application/vnd.google-apps.folder',
  size: null,
  downloadable: false,
  starred: false,
};
const ITEMS = [
  item('d1', 'Projects 2026', FOLDER),
  item('s1', 'Launch plan', {
    kind: 'shortcut',
    mime_type: 'application/vnd.google-apps.shortcut',
    size: null,
    target_id: 'g1',
    target_kind: 'file',
    downloadable: false,
    starred: false,
  }),
  item('g1', 'Committee minutes', {
    mime_type: 'application/vnd.google-apps.document',
    size: null,
    formats: ['pdf', 'docx'],
  }),
  item('p1', 'Customer deck.pdf', { size: CEILING + 1 }),
];

function detail(base: Record<string, unknown>, extra: Record<string, unknown> = {}) {
  return {
    ...base,
    owners: ['Ana Lima'],
    description: null,
    created_at: '2026-03-12T10:00:00Z',
    ancestors: [],
    in_my_drive: true,
    ancestors_truncated: false,
    ...extra,
  };
}

const DETAILS: Record<string, unknown> = {
  d1: detail(ITEMS[0]),
  g1: detail(ITEMS[2], { ancestors: [{ id: 'd1', name: 'Projects 2026' }] }),
  p1: detail(ITEMS[3]),
  w1: detail(item('w1', 'Budget.xlsx', { previewable: true })),
  t1: detail(item('t1', 'Notes.txt', { mime_type: 'text/plain', editable: true })),
  v1: detail(item('v1', 'Report.pdf', { mime_type: 'application/pdf', previewable: true })),
  v2: detail(item('v2', 'Report.docx', { previewable: true })),
  v3: detail(item('v3', 'Notes.md', { previewable: true })),
};

const VIEWERS = join(__dirname, '../fixtures/viewers');
const WORD_TYPE = 'application/vnd.openxmlformats-officedocument.wordprocessingml.document';

/** The reading door, answering one file. */
function reading(contentType: string, body: Buffer | string): MockRoute {
  return {
    url: '**/api/v1/workbench/files/preview?*',
    method: 'GET',
    handler: async route => {
      await route.fulfill({
        contentType,
        headers: { 'X-Preview-Truncated': 'false' },
        body,
      });
    },
  };
}

/** What the browser says it refused: the page's own policy is what is proven here. */
function refusals(page: Page): string[] {
  const refused: string[] = [];
  page.on('console', message => {
    if (/Content Security Policy|Refused to/i.test(message.text())) refused.push(message.text());
  });
  return refused;
}

const SHARING = {
  people: [{ id: 'p0', email: 'ana@example.org', name: 'Ana Lima', role: 'owner' }],
  link: null,
};

async function playTheApi(
  mockApi: (routes: MockRoute[]) => Promise<void>,
  extra: MockRoute[] = []
) {
  await mockApi([
    ...extra,
    { url: '**/api/v1/workbench/files/quota', json: { used: 3000, total: 10000 } },
    { url: '**/api/v1/workbench/files/sharing?*', method: 'GET', json: SHARING },
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
      url: '**/api/v1/workbench/files/file*',
      handler: async route => {
        const id = new URL(route.request().url()).searchParams.get('id') ?? '';
        await route.fulfill({ json: DETAILS[id] });
      },
    },
    {
      url: '**/api/v1/workbench/files*',
      method: 'GET',
      json: { items: ITEMS, next_page_token: 'n2' },
    },
  ]);
}

for (const sample of [
  { width: 1280, theme: 'light', query: '' },
  { width: 1280, theme: 'dark', query: '?folder=d1&file=g1' },
  { width: 390, theme: 'oled', query: '?file=p1' },
] as const) {
  test(`files screen at ${sample.width}px in ${sample.theme}`, async ({
    page,
    authenticate,
    mockApi,
  }) => {
    await page.setViewportSize({ width: sample.width, height: 900 });
    await prepareTheme(page, sample.theme);
    await authenticate({ timezone: 'Europe/Paris' });
    await playTheApi(mockApi);

    await page.goto(`/en/dashboard/tools/files${sample.query}`);
    await waitForHydration(page, 'main');
    // Below `lg` an open file takes the list's place: wait on what the screen shows.
    await expect(
      sample.query.includes('file=')
        ? page.getByRole('article').first()
        : page.getByRole('searchbox', { name: 'Search Drive' })
    ).toBeVisible();

    await expectNoOverflow(page, `${sample.width}px ${sample.theme}`);
    const scan = await new AxeBuilder({ page }).include('main').analyze();
    expect(scan.violations).toEqual([]);
  });
}

/** Records what a route is asked, and answers it. */
function recorded(url: string, json: unknown, status = 200) {
  const bodies: unknown[] = [];
  const route: MockRoute = {
    url,
    method: 'POST',
    handler: async called => {
      bodies.push(called.request().postDataJSON());
      await called.fulfill({ status, json });
    },
  };
  return { bodies, route };
}

test.describe('organising, on a phone', () => {
  test.beforeEach(async ({ page, authenticate }) => {
    await page.setViewportSize({ width: 390, height: 844 });
    await authenticate({ timezone: 'Europe/Paris' });
  });

  test('a file moves through a walk of the folders', async ({ page, mockApi }) => {
    const move = recorded('**/api/v1/workbench/files/move', { done: ['g1'], failed: [] });
    await playTheApi(mockApi, [move.route]);

    await page.goto('/en/dashboard/tools/files?file=p1');
    await waitForHydration(page, 'article');
    await page.getByRole('button', { name: 'Organise' }).click();
    await page.getByRole('menuitem', { name: 'Move' }).click();

    const dialog = page.getByRole('dialog');
    await expect(dialog.getByRole('button', { name: 'Move here' })).toBeDisabled();
    await dialog.getByRole('button', { name: 'Projects 2026' }).click();
    await expectNoOverflow(page, 'the walk at 390px');
    await dialog.getByRole('button', { name: 'Move here' }).click();

    await expect(dialog).toBeHidden();
    expect(move.bodies).toEqual([{ file_ids: ['p1'], folder_id: 'd1' }]);
  });

  test('a file really chosen is sent to the folder the list stands in', async ({
    page,
    mockApi,
  }) => {
    const sent: string[] = [];
    await playTheApi(mockApi, [
      {
        url: '**/api/v1/workbench/files/upload',
        method: 'POST',
        handler: async called => {
          sent.push(called.request().postData() ?? '');
          await called.fulfill({ status: 201, json: item('u1', 'Notes.txt') });
        },
      },
    ]);

    await page.goto('/en/dashboard/tools/files?folder=d1');
    await waitForHydration(page, 'form[role="search"]');
    await page.getByLabel('Send files to this folder').setInputFiles({
      name: 'Notes.txt',
      mimeType: 'text/plain',
      buffer: Buffer.from('hello'),
    });

    await expect(page.getByText('File sent')).toBeVisible();
    expect(sent).toHaveLength(1);
    expect(sent[0]).toContain('name="name"');
    expect(sent[0]).toContain('Notes.txt');
    expect(sent[0]).toContain('name="folder_id"');
    expect(sent[0]).toContain('hello');
  });

  test('a new folder takes its name in a dialog held within the screen', async ({
    page,
    mockApi,
  }) => {
    const folder = recorded('**/api/v1/workbench/files/folders', item('n1', 'Trips', FOLDER), 201);
    await playTheApi(mockApi, [folder.route]);

    await page.goto('/en/dashboard/tools/files');
    await waitForHydration(page, 'form[role="search"]');
    await page.getByRole('button', { name: 'New folder' }).click();
    const dialog = page.getByRole('dialog');
    await dialog.getByRole('textbox').fill('Trips');
    await expectNoOverflow(page, 'the name at 390px');
    await dialog.getByRole('button', { name: 'Create' }).click();

    await expect(dialog).toBeHidden();
    expect(folder.bodies).toEqual([
      expect.objectContaining({
        name: 'Trips',
        folder_id: null,
        idempotency_key: expect.any(String),
      }),
    ]);
  });

  test('a person is given access, and the drive tells them', async ({ page, mockApi }) => {
    const share = recorded('**/api/v1/workbench/files/sharing', {}, 200);
    await playTheApi(mockApi, [share.route]);

    await page.goto('/en/dashboard/tools/files?file=p1');
    await waitForHydration(page, 'article');
    await page.getByRole('button', { name: 'Organise' }).click();
    await page.getByRole('menuitem', { name: 'Share' }).click();

    const dialog = page.getByRole('dialog');
    await expect(dialog.getByText('Ana Lima')).toBeVisible();
    await dialog.getByRole('textbox', { name: 'Their e-mail address' }).fill('bob@example.org');
    await expectNoOverflow(page, 'sharing at 390px');
    await dialog.getByRole('button', { name: 'Share' }).click();

    await expect(page.getByText('Shared: the drive told them')).toBeVisible();
    expect(share.bodies).toEqual([
      expect.objectContaining({ file_id: 'p1', email: 'bob@example.org', role: 'reader' }),
    ]);
  });

  test('the views stay within the screen, and the trash asks before it empties', async ({
    page,
    mockApi,
  }) => {
    const empty = recorded('**/api/v1/workbench/files/trash/empty', {});
    await playTheApi(mockApi, [empty.route]);

    await page.goto('/en/dashboard/tools/files');
    await waitForHydration(page, 'form[role="search"]');
    const views = page.getByRole('navigation', { name: 'Views of the drive' });
    await expect(views.getByRole('link')).toHaveCount(6);
    await expectNoOverflow(page, 'the views at 390px');
    await views.getByRole('link', { name: 'Trash' }).click();

    await expect(page).toHaveURL(/\?view=trash$/);
    await page.getByRole('button', { name: 'Empty the trash' }).click();
    await page.getByRole('alertdialog').getByRole('button', { name: 'Empty the trash' }).click();

    await expect(page.getByText('Trash emptied')).toBeVisible();
    expect(empty.bodies).toHaveLength(1);
  });
});

/**
 * Owner request (2026-11-05): a file read before it is opened, whole where a browser can show it,
 * changed here when it is a text. A workbook is laid out, a sheet at a time.
 */
test('a workbook is laid out a sheet at a time, and takes a window', async ({
  page,
  authenticate,
  mockApi,
}) => {
  await authenticate({ timezone: 'Europe/Paris' });
  await playTheApi(mockApi, [
    {
      url: '**/api/v1/workbench/files/preview?*',
      method: 'GET',
      handler: async route => {
        await route.fulfill({
          contentType: 'application/json',
          headers: { 'X-Preview-Truncated': 'true' },
          body: JSON.stringify({
            sheets: [
              {
                name: 'Budget',
                rows: [
                  ['Item', 'Cost'],
                  ['Rent', '700'],
                ],
                cut: false,
              },
              { name: 'Team', rows: [['Ana']], cut: true },
            ],
          }),
        });
      },
    },
  ]);

  await page.goto('/en/dashboard/tools/files?file=w1');
  await expect(page.getByRole('cell', { name: 'Rent' })).toBeVisible();

  await page.getByRole('button', { name: 'Team' }).click();
  await expect(page.getByRole('cell', { name: 'Ana' })).toBeVisible();
  await expect(page.getByRole('cell', { name: 'Rent' })).toHaveCount(0);

  await page.getByRole('button', { name: 'Enlarge' }).click();
  const window = page.getByRole('dialog');
  await expect(window.getByRole('cell', { name: 'Rent' })).toBeVisible();
  expect((await new AxeBuilder({ page }).include('[role="dialog"]').analyze()).violations).toEqual(
    []
  );
});

test('a PDF is read in the page, every page of it, its words selectable', async ({
  page,
  authenticate,
  mockApi,
}) => {
  const refused = refusals(page);
  const runtime: Array<[string, number]> = [];
  page.on('response', response => {
    if (response.url().includes('/pdfjs/')) runtime.push([response.url(), response.status()]);
  });
  await authenticate({ timezone: 'Europe/Paris' });
  await playTheApi(mockApi, [
    reading('application/pdf', readFileSync(join(VIEWERS, 'report.pdf'))),
  ]);

  await page.goto('/en/dashboard/tools/files?file=v1');
  await expect(page.getByText('3 pages')).toBeVisible();

  const first = page.getByRole('group', { name: 'Page 1' });
  await expect(first.getByText('First page of proof')).toBeAttached();
  const ink = await first.locator('canvas').evaluate(canvas => {
    if (!(canvas instanceof HTMLCanvasElement)) return 0;
    const drawing = canvas.getContext('2d');
    if (!drawing) return 0;
    const { data } = drawing.getImageData(0, 0, canvas.width, canvas.height);
    let dark = 0;
    for (let index = 0; index < data.length; index += 4) if ((data[index] ?? 255) < 128) dark += 1;
    return dark;
  });
  expect(ink).toBeGreaterThan(200);

  await page.getByRole('button', { name: 'Enlarge' }).click();
  const window = page.getByRole('dialog');
  await expect(window.getByText('3 pages')).toBeVisible();
  const before = (await window.getByRole('group', { name: 'Page 1' }).boundingBox())?.width ?? 0;
  await window.getByRole('button', { name: 'Zoom in' }).click();
  await expect
    .poll(async () => (await window.getByRole('group', { name: 'Page 1' }).boundingBox())?.width)
    .toBeGreaterThan(before * 1.4);
  await window.getByRole('group', { name: 'Page 3' }).scrollIntoViewIfNeeded();
  await expect(window.getByText('Third page of proof')).toBeAttached();

  expect(refused).toEqual([]);
  expect(runtime.length).toBeGreaterThan(0);
  expect(runtime.filter(([, status]) => status !== 200 && status !== 304)).toEqual([]);
  expect((await new AxeBuilder({ page }).include('[role="dialog"]').analyze()).violations).toEqual(
    []
  );
});

test('a Word file keeps its layout, in a frame that reaches nothing', async ({
  page,
  authenticate,
  mockApi,
}) => {
  const refused = refusals(page);
  await authenticate({ timezone: 'Europe/Paris' });
  await playTheApi(mockApi, [reading(WORD_TYPE, readFileSync(join(VIEWERS, 'report.docx')))]);

  await page.goto('/en/dashboard/tools/files?file=v2');

  const frame = page.frameLocator('iframe[title="Report.docx"]');
  await expect(frame.getByText('Proof report')).toBeVisible();
  await expect(frame.getByRole('cell', { name: 'Rent' })).toBeVisible();
  await expect(frame.locator('b, strong, [style*="bold"], span').first()).toBeAttached();
  const picture = frame.locator('img');
  await expect(picture).toBeVisible();
  expect(await picture.evaluate(image => (image as HTMLImageElement).naturalWidth)).toBeGreaterThan(
    0
  );
  await expect(frame.getByRole('link', { name: 'link' })).toHaveAttribute('target', '_blank');
  expect(refused).toEqual([]);
});

test('a hostile Word file runs nothing', async ({ page, authenticate, mockApi }) => {
  let alerted = false;
  page.on('dialog', async dialog => {
    alerted = true;
    await dialog.dismiss();
  });
  await authenticate({ timezone: 'Europe/Paris' });
  await playTheApi(mockApi, [reading(WORD_TYPE, readFileSync(join(VIEWERS, 'hostile.docx')))]);

  await page.goto('/en/dashboard/tools/files?file=v2');

  const frame = page.frameLocator('iframe[title="Report.docx"]');
  await expect(frame.getByText('Hostile words')).toBeVisible();
  await frame.getByText('a trap').click();
  await expect(frame.getByText('Hostile words')).toBeVisible();
  expect(alerted).toBe(false);
});

test('a Markdown is laid out, and fits a phone', async ({ page, authenticate, mockApi }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await authenticate({ timezone: 'Europe/Paris' });
  await playTheApi(mockApi, [
    reading('text/markdown', '# Meeting notes\n\n| Item | Cost |\n|---|---|\n| Rent | 700 |\n'),
  ]);

  await page.goto('/en/dashboard/tools/files?file=v3');

  await expect(page.getByRole('heading', { name: 'Meeting notes' })).toBeVisible();
  await expect(page.getByRole('cell', { name: 'Rent' })).toBeVisible();
  await expectNoOverflow(page, 'a Markdown at 390px');
});

test('a reading the server refused once is read again on a click', async ({
  page,
  authenticate,
  mockApi,
}) => {
  let reads = 0;
  await authenticate({ timezone: 'Europe/Paris' });
  await playTheApi(mockApi, [
    {
      url: '**/api/v1/workbench/files/preview?*',
      method: 'GET',
      handler: async route => {
        reads += 1;
        if (reads === 1) {
          await route.fulfill({
            status: 429,
            contentType: 'application/json',
            body: JSON.stringify({
              detail: { code: 'provider_rate_limited', retry_after: 5 },
            }),
          });
          return;
        }
        await route.fulfill({ contentType: 'text/plain', body: 'Hello there' });
      },
    },
  ]);

  await page.goto('/en/dashboard/tools/files?file=v3');

  const again = page.getByRole('button', { name: 'Try again' });
  await expect(again).toBeVisible();
  expect(reads).toBe(1);
  await again.click();
  await expect(page.getByText('Hello there')).toBeVisible();
});

test('a text is changed on the version it was read at, and a change elsewhere keeps the words', async ({
  page,
  authenticate,
  mockApi,
}) => {
  const written: Array<Record<string, unknown>> = [];
  await authenticate({ timezone: 'Europe/Paris' });
  await playTheApi(mockApi, [
    { url: '**/api/v1/workbench/files/text?*', json: { text: 'Hello', tag: 'tag-1' } },
    {
      url: '**/api/v1/workbench/files/text',
      method: 'PUT',
      handler: async route => {
        written.push(route.request().postDataJSON() as Record<string, unknown>);
        if (written.length === 1) {
          await route.fulfill({ status: 409, json: { detail: { code: 'conflict' } } });
          return;
        }
        await route.fulfill({ json: DETAILS.t1 });
      },
    },
  ]);

  await page.goto('/en/dashboard/tools/files?file=t1');
  await page.getByRole('button', { name: 'Edit the text' }).click();
  const field = page.getByRole('textbox', { name: 'Text of the file' });
  await expect(field).toHaveValue('Hello');
  await expect(page.getByRole('button', { name: 'Save' })).toBeDisabled();

  await field.fill('Hello world');
  await page.getByRole('button', { name: 'Save' }).click();
  await expect(page.getByRole('alert')).toContainText('changed elsewhere');
  await expect(field).toHaveValue('Hello world');
  expect((await new AxeBuilder({ page }).include('[role="dialog"]').analyze()).violations).toEqual(
    []
  );

  await page.getByRole('button', { name: 'Take the current version' }).click();
  await expect(field).toHaveValue('Hello');
  await field.fill('Bye');
  await page.getByRole('button', { name: 'Save' }).click();

  await expect(field).toHaveCount(0);
  expect(written.at(-1)).toEqual({ id: 't1', text: 'Bye', tag: 'tag-1' });
});

test('a folder opens in the list, under its breadcrumb', async ({
  page,
  authenticate,
  mockApi,
}) => {
  await page.setViewportSize({ width: 1280, height: 900 });
  await authenticate({ timezone: 'Europe/Paris' });
  await playTheApi(mockApi);

  await page.goto('/en/dashboard/tools/files');
  await waitForHydration(page, 'form[role="search"]');
  await page.getByRole('link', { name: /Projects 2026/ }).click();

  await expect(page).toHaveURL(/\/en\/dashboard\/tools\/files\?folder=d1$/);
  const crumbs = page.getByRole('navigation', { name: 'Folders' });
  await expect(crumbs.getByRole('link', { name: 'My Drive' })).toBeVisible();
  await expect(crumbs.getByText('Projects 2026')).toHaveAttribute('aria-current', 'page');
});

test('a Google document downloads once per format, through the API', async ({
  page,
  authenticate,
  mockApi,
}) => {
  await page.setViewportSize({ width: 1280, height: 900 });
  await authenticate({ timezone: 'Europe/Paris' });
  await playTheApi(mockApi);

  await page.goto('/en/dashboard/tools/files?file=g1');
  const article = page.getByRole('article', { name: 'Committee minutes' });
  const links = article.getByRole('link', { name: /^Download as / });
  await expect(links).toHaveCount(2);
  for (const [index, format] of ['pdf', 'docx'].entries()) {
    await expect(links.nth(index)).toHaveAttribute(
      'href',
      new RegExp(`/api/v1/workbench/files/download\\?id=g1&format=${format}$`)
    );
    await expect(links.nth(index)).toHaveAttribute('rel', 'noopener noreferrer');
  }
  await expect(article.getByRole('link', { name: 'Open in Drive' })).toHaveAttribute(
    'rel',
    'noopener noreferrer'
  );
});

test('a file past the ceiling is said, never offered', async ({ page, authenticate, mockApi }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await authenticate({ timezone: 'Europe/Paris' });
  await playTheApi(mockApi);

  await page.goto('/en/dashboard/tools/files?file=p1');
  const article = page.getByRole('article', { name: 'Customer deck.pdf' });
  await expect(article.getByText(/^Larger than .*: open it in Drive$/)).toBeVisible();
  await expect(article.getByRole('link', { name: /^Download/ })).toHaveCount(0);
});

test('the keyboard opens a file and gets its row back when it closes', async ({
  page,
  authenticate,
  mockApi,
}) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await authenticate({ timezone: 'Europe/Paris' });
  await playTheApi(mockApi);

  await page.goto('/en/dashboard/tools/files');
  await waitForHydration(page, 'form[role="search"]');
  const link = page.getByRole('link', { name: /Customer deck\.pdf/ });
  await link.focus();
  await page.keyboard.press('Enter');

  const close = page.getByRole('button', { name: 'Files' });
  await expect(close).toBeFocused();
  await expectNoOverflow(page, 'detail at 390px');
  await page.keyboard.press('Enter');

  await expect(page.getByRole('link', { name: /Customer deck\.pdf/ })).toBeFocused();
});
