/**
 * The « Tools » contacts screen, hermetic (ADR-369, Task 7.2).
 *
 * The API is played by the spec: one ready Google contacts provider with
 * groups, a page that says more exists, one contact whose name folds exactly
 * to a known relationship. Proven at 1280 and 390 px, in light, dark and OLED:
 * no horizontal scroll, axe clean on the screen; « See the relationship »
 * opens the Relations page on that person; a change sends only the list it
 * changed; the keyboard opens a contact and gets its row back when it closes;
 * a contact shows its job, website, birthday and groups, and its editor fits a phone.
 */
import AxeBuilder from '@axe-core/playwright';
import type { Route } from '@playwright/test';

import { test, expect, waitForHydration } from '../fixtures';
import type { MockRoute } from '../fixtures/api-mock';
import { appConfig } from '../fixtures/dashboard-shell';
import { expectNoOverflow, prepareTheme } from './overflow-report';

const RAIL = {
  tools: ['mail', 'calendar', 'tasks', 'contacts', 'files', 'lights'].map(tool =>
    tool === 'contacts'
      ? {
          tool,
          state: 'ready',
          provider: 'google_contacts',
          features: ['multi_valued', 'contact_groups', 'other_contacts'],
          bounds: {
            name_max_chars: 512,
            notes_max_chars: 8192,
            value_max_chars: 320,
            values_max: 20,
            photo_max_bytes: 10485760,
            history_addresses: 3,
            export_max_contacts: 1000,
            import_max_cards: 100,
            import_max_bytes: 5242880,
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
  },
};

const ANA = {
  id: 'people/c1',
  name: 'Ana Lima',
  given_name: 'Ana',
  family_name: 'Lima',
  email: 'ana@example.org',
  phone: '+33 6 12 34 56 78',
  organization: 'Atlas',
  name_key: 'ana lima',
  emails: [{ value: 'ana@example.org', type: 'work' }],
  phones: [{ value: '+33 6 12 34 56 78', type: 'mobile' }],
  addresses: [{ formatted: '3 place de la Bourse, 69002 Lyon', type: 'work' }],
  notes: 'Met at the fair.',
  job_title: 'Engineer',
  website: 'https://ana.example.org',
  birthday: '1990-05-15',
};
const ROWS = [
  ANA,
  {
    id: 'people/c2',
    // As Outlook files a contact by default: the list still reads « Given Family ».
    name: 'Moreau, Inès',
    given_name: 'Inès',
    family_name: 'Moreau',
    email: 'ines@example.org',
    phone: null,
    organization: null,
    name_key: 'ines moreau',
  },
];

/** The latest exchanges with Ana: long subjects, to prove they fit a phone. */
const HISTORY = {
  mail: 'used',
  received: [
    {
      id: 'm1',
      subject: 'A subject long enough to run past the width of any phone in the hand',
      at: '2026-11-03T09:00:00Z',
    },
  ],
  sent: [{ id: 'm2', subject: 'My answer', at: '2026-11-02T09:00:00Z' }],
  calendar: 'used',
  organized_by_them: [
    {
      id: 'e1',
      title: 'Quarterly review',
      at: '2026-11-01T09:00:00Z',
      day: '2026-11-01',
      all_day: false,
      calendar_id: 'primary',
    },
  ],
  organized_by_you: [],
  shared: [],
  meetings_window_days: 720,
  meetings_cut: false,
};

let patched: unknown[] = [];

async function answer(route: Route): Promise<void> {
  const request = route.request();
  const path = new URL(request.url()).pathname;
  if (request.method() === 'PATCH') {
    patched.push(request.postDataJSON());
    await route.fulfill({ json: ANA });
    return;
  }
  if (path.endsWith('/contacts/history')) {
    await route.fulfill({ json: HISTORY });
    return;
  }
  if (path.endsWith('/contacts/groups')) {
    await route.fulfill({
      json: { groups: [{ id: 'contactGroups/f', name: 'Friends', count: 7, own: true }] },
    });
    return;
  }
  if (path.endsWith('/contacts/member-of')) {
    await route.fulfill({
      json: { groups: [{ id: 'contactGroups/f', name: 'Friends', count: 7, own: true }] },
    });
    return;
  }
  if (path.endsWith('/contacts/photo')) {
    await route.fulfill({ status: 404, json: { detail: { code: 'item_gone' } } });
    return;
  }
  if (path.endsWith('/contacts/contact')) {
    await route.fulfill({ json: ANA });
    return;
  }
  await route.fulfill({ json: { items: ROWS, next_page_token: 'n2', truncated: false } });
}

async function playTheApi(mockApi: (routes: MockRoute[]) => Promise<void>) {
  patched = [];
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
    { url: '**/api/v1/workbench/contacts**', handler: answer },
    {
      url: '**/api/v1/relations',
      json: { relations: [{ display_name: 'Ana LIMA', name_key: 'ana lima' }], relations_total: 1 },
    },
  ]);
}

for (const sample of [
  { width: 1280, theme: 'light', query: '' },
  { width: 1280, theme: 'dark', query: '?contact=people%2Fc1' },
  { width: 390, theme: 'oled', query: '?contact=people%2Fc1' },
] as const) {
  test(`contacts screen at ${sample.width}px in ${sample.theme}`, async ({
    page,
    authenticate,
    mockApi,
  }) => {
    await page.setViewportSize({ width: sample.width, height: 900 });
    await prepareTheme(page, sample.theme);
    await authenticate({ timezone: 'Europe/Paris' });
    await playTheApi(mockApi);

    await page.goto(`/en/dashboard/tools/contacts${sample.query}`);
    await waitForHydration(page, 'main');
    // Below `lg` an open contact takes the list's place: wait on what the screen shows.
    await expect(
      sample.query
        ? page.getByRole('article', { name: 'Ana Lima' })
        : page.getByRole('link', { name: /Ana Lima/ })
    ).toBeVisible();

    await expectNoOverflow(page, `${sample.width}px ${sample.theme}`);
    const scan = await new AxeBuilder({ page }).include('main').analyze();
    expect(scan.violations).toEqual([]);
  });
}

/** Owner request (2026-10-31): « Given Family », in the order the API sorted (family, given). */
/**
 * Owner request (2026-11-05): a contact's latest mail and meetings, cleanly laid out. On a wide
 * panel they stand beside the card, with no scrolling to reach them; on a middle one under it,
 * mail and meetings side by side; on a phone one under the other. A line opens in its own tool.
 */
for (const sample of [
  { width: 1600, besideTheCard: true, sideBySide: false },
  { width: 1280, besideTheCard: false, sideBySide: true },
  { width: 390, besideTheCard: false, sideBySide: false },
] as const) {
  test(`a contact's exchanges hold at ${sample.width}px`, async ({
    page,
    authenticate,
    mockApi,
  }) => {
    await page.setViewportSize({ width: sample.width, height: 900 });
    await authenticate({ timezone: 'Europe/Paris' });
    await playTheApi(mockApi);

    await page.goto('/en/dashboard/tools/contacts?contact=people%2Fc1');
    const history = page.getByRole('region', { name: 'Latest exchanges' });
    const mail = history.getByRole('region', { name: 'Mail' });
    const meetings = history.getByRole('region', { name: 'Meetings' });
    await expect(mail.getByRole('link', { name: /My answer/ })).toBeVisible();
    await expect(meetings.getByText('Organised by Ana Lima')).toBeVisible();
    await expect(meetings.getByText('Over the last 24 months.')).toBeVisible();

    const card = await page.getByRole('heading', { level: 2, name: 'Ana Lima' }).boundingBox();
    const panel = await history.boundingBox();
    const left = await mail.boundingBox();
    const right = await meetings.boundingBox();
    if (card === null || panel === null || left === null || right === null) {
      throw new Error('not drawn');
    }
    expect(panel.x > card.x + 200).toBe(sample.besideTheCard);
    expect(right.y === left.y).toBe(sample.sideBySide);

    await expectNoOverflow(page, `exchanges ${sample.width}px`);
    const scan = await new AxeBuilder({ page }).include('main').analyze();
    expect(scan.violations).toEqual([]);

    await mail.getByRole('link', { name: /My answer/ }).click();
    await expect(page).toHaveURL(/\/tools\/mail\?folder=system%3Asent&id=m2/);
  });
}

test('the list reads « Given Family », in the order the API sorted', async ({
  page,
  authenticate,
  mockApi,
}) => {
  await page.setViewportSize({ width: 1280, height: 900 });
  await authenticate({ timezone: 'Europe/Paris' });
  await playTheApi(mockApi);

  await page.goto('/en/dashboard/tools/contacts');
  await waitForHydration(page, 'main');
  await expect(page.getByRole('link', { name: /Inès Moreau/ })).toBeVisible();
  const names = await page
    .getByRole('link', { name: /Ana Lima|Inès Moreau/ })
    .evaluateAll(links => links.map(link => link.querySelector('.font-medium')?.textContent ?? ''));
  expect(names).toEqual(['Ana Lima', 'Inès Moreau']);
  await expect(page.getByText('Moreau, Inès')).toHaveCount(0);
});

test('« See the relationship » opens the Relations page on that person', async ({
  page,
  authenticate,
  mockApi,
}) => {
  await page.setViewportSize({ width: 1280, height: 900 });
  await authenticate({ timezone: 'Europe/Paris' });
  await playTheApi(mockApi);

  await page.goto('/en/dashboard/tools/contacts?contact=people%2Fc1');
  const link = page.getByRole('link', { name: 'See the relationship' });
  await expect(link).toHaveAttribute('href', '/en/dashboard/relations?name=Ana+LIMA');
});

test('a change sends only the list it changed', async ({ page, authenticate, mockApi }) => {
  await page.setViewportSize({ width: 1280, height: 900 });
  await authenticate({ timezone: 'Europe/Paris' });
  await playTheApi(mockApi);

  await page.goto('/en/dashboard/tools/contacts?contact=people%2Fc1');
  await page.getByRole('button', { name: 'Edit' }).click();
  const dialog = page.getByRole('dialog');
  await dialog.getByRole('button', { name: 'Add a phone number' }).click();
  await dialog.getByLabel('Phone number 2').fill('+33 1 00 00 00 00');
  await dialog.getByRole('button', { name: 'Save' }).click();

  await expect(dialog).toBeHidden();
  expect(patched).toEqual([
    {
      id: 'people/c1',
      phones: [
        { value: '+33 6 12 34 56 78', type: 'mobile' },
        { value: '+33 1 00 00 00 00', type: 'mobile' },
      ],
    },
  ]);
});

test('a contact shows all it holds, and its editor fits a phone', async ({
  page,
  authenticate,
  mockApi,
}) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await authenticate({ timezone: 'Europe/Paris' });
  await playTheApi(mockApi);

  await page.goto('/en/dashboard/tools/contacts?contact=people/c1');
  const contact = page.getByRole('article', { name: 'Ana Lima' });
  await expect(contact.getByText('Engineer · Atlas')).toBeVisible();
  await expect(contact.getByRole('link', { name: 'https://ana.example.org' })).toBeVisible();
  await expect(contact.getByText('May 15, 1990')).toBeVisible();
  await expect(contact.getByRole('listitem').filter({ hasText: 'Friends' })).toBeVisible();
  await expect(contact.getByRole('link', { name: 'Export' })).toHaveAttribute(
    'href',
    /contacts\/export\?id=people%2Fc1/
  );
  await expectNoOverflow(page, 'a contact at 390px');
  const scan = await new AxeBuilder({ page }).include('main').analyze();
  expect(scan.violations).toEqual([]);

  await contact.getByRole('button', { name: 'Edit' }).click();
  const editor = page.getByRole('dialog');
  await expect(editor.getByLabel('Given name')).toHaveValue('Ana');
  await expect(editor.getByLabel('Birthday')).toHaveValue('1990-05-15');
  await editor.getByLabel('Job title').fill('CTO');
  await expectNoOverflow(page, 'the editor at 390px');
  await editor.getByRole('button', { name: 'Save' }).click();

  await expect.poll(() => patched).toEqual([{ id: 'people/c1', job_title: 'CTO' }]);
});

test('the keyboard opens a contact and gets its row back when it closes', async ({
  page,
  authenticate,
  mockApi,
}) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await authenticate({ timezone: 'Europe/Paris' });
  await playTheApi(mockApi);

  await page.goto('/en/dashboard/tools/contacts');
  await waitForHydration(page, 'form[role="search"]');
  const link = page.getByRole('link', { name: /Ana Lima/ });
  await link.focus();
  await page.keyboard.press('Enter');

  const close = page.getByRole('button', { name: 'Contacts' });
  await expect(close).toBeFocused();
  await expectNoOverflow(page, 'contact at 390px');
  await page.keyboard.press('Enter');

  await expect(page.getByRole('link', { name: /Ana Lima/ })).toBeFocused();
});
