/**
 * The « Tools » files screen, hermetic (ADR-369, Task 8.2).
 *
 * The API is played by the spec: one ready Drive, a folder holding a folder, a
 * shortcut, a Google document and a file past the ceiling. Proven at 1280 and
 * 390 px, in light, dark and OLED: no horizontal scroll, axe clean on the
 * screen; a folder opens in the list with its breadcrumb; a Google document
 * downloads once per format through the API, in a tab that cannot reach back;
 * a file past the ceiling is said, never offered; the keyboard opens a file and
 * gets its row back when it closes.
 */
import AxeBuilder from '@axe-core/playwright';

import { test, expect, waitForHydration } from '../fixtures';
import type { MockRoute } from '../fixtures/api-mock';
import { appConfig } from '../fixtures/dashboard-shell';
import { expectNoOverflow, prepareTheme } from './overflow-report';

const CEILING = 26214400;

const RAIL = {
  tools: ['mail', 'calendar', 'tasks', 'contacts', 'files', 'lights'].map(tool =>
    tool === 'files'
      ? { tool, state: 'ready', provider: 'google_drive', features: ['export'], bounds: {} }
      : { tool, state: 'not_connected', provider: null, features: [], bounds: {} }
  ),
  limits: {
    page_size: 25,
    bulk_max_items: 50,
    download_max_bytes: CEILING,
    calendar_window_max_events: 500,
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
    ...extra,
  };
}

const FOLDER = {
  kind: 'folder',
  mime_type: 'application/vnd.google-apps.folder',
  size: null,
  downloadable: false,
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
};

async function playTheApi(mockApi: (routes: MockRoute[]) => Promise<void>) {
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

  const close = page.getByRole('button', { name: 'Close the file' });
  await expect(close).toBeFocused();
  await expectNoOverflow(page, 'detail at 390px');
  await page.keyboard.press('Enter');

  await expect(page.getByRole('link', { name: /Customer deck\.pdf/ })).toBeFocused();
});
