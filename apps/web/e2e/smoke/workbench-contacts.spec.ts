/**
 * The « Tools » contacts screen, hermetic (ADR-369, Task 7.2).
 *
 * The API is played by the spec: one ready Google contacts provider with
 * groups, a page that says more exists, one contact whose name folds exactly
 * to a known relationship. Proven at 1280 and 390 px, in light, dark and OLED:
 * no horizontal scroll, axe clean on the screen; « See the relationship »
 * opens the Relations page on that person; a change sends only the list it
 * changed; the keyboard opens a contact and gets its row back when it closes.
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

let patched: unknown[] = [];

async function answer(route: Route): Promise<void> {
  const request = route.request();
  const path = new URL(request.url()).pathname;
  if (request.method() === 'PATCH') {
    patched.push(request.postDataJSON());
    await route.fulfill({ json: ANA });
    return;
  }
  if (path.endsWith('/contacts/groups')) {
    await route.fulfill({
      json: { groups: [{ id: 'contactGroups/f', name: 'Friends', count: 7 }] },
    });
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
    .evaluateAll(links => links.map(link => link.firstElementChild?.textContent ?? ''));
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

  const close = page.getByRole('button', { name: 'Close the contact' });
  await expect(close).toBeFocused();
  await expectNoOverflow(page, 'contact at 390px');
  await page.keyboard.press('Enter');

  await expect(page.getByRole('link', { name: /Ana Lima/ })).toBeFocused();
});
