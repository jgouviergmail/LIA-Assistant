/** Consumption CSVs: responsive collection, real downloads and user/admin isolation. */
import { readFileSync } from 'node:fs';
import path from 'node:path';
import type { Locator, Page, TestInfo } from '@playwright/test';
import {
  test,
  expect,
  waitForHydration,
  idleNotificationStream,
  expectSessionCookie,
} from '../fixtures';
import { scanPage } from '../a11y/scan';
import { expectNoOverflow, prepareTheme } from './overflow-report';

const translations: unknown = JSON.parse(
  readFileSync(path.join(__dirname, '../../locales/fr/translation.json'), 'utf8')
);
const TYPES = [
  'token-usage',
  'google-api-usage',
  'stt-usage',
  'tts-usage',
  'consumption-summary',
] as const;
const KEYS = ['token_usage', 'google_api_usage', 'stt_usage', 'tts_usage', 'summary'] as const;
const CSV = 'date,cost_eur\n2026-10-01,0.0123\n';
function copy(key: string): string {
  let value: unknown = translations;
  for (const part of key.split('.')) {
    if (!value || typeof value !== 'object') throw new Error(`Missing French label: ${key}`);
    value = (value as Record<string, unknown>)[part];
  }
  if (typeof value !== 'string') throw new Error(`Missing French label: ${key}`);
  return value;
}
function section(page: Page, mode: 'user' | 'admin' = 'user') {
  return page.locator(`#settings-section-${mode}-consumption-export`);
}
function row(page: Page, index: number, mode: 'user' | 'admin' = 'user') {
  return section(page, mode).getByRole('listitem').nth(index);
}
function button(page: Page, index: number, mode: 'user' | 'admin' = 'user') {
  return row(page, index, mode).getByRole('button', {
    name: `${copy(`settings.${mode}.export.download`)} ${copy(`settings.${mode}.export.${KEYS[index]}_title`)}`,
    exact: true,
  });
}
async function box(element: Locator) {
  const result = await element.boundingBox();
  expect(result).not.toBeNull();
  return result!;
}
async function open(page: Page, mode: 'user' | 'admin' = 'user') {
  const response = await page.goto(`/fr/dashboard/settings?section=${mode}-consumption-export`);
  expect(response?.status()).toBe(200);
  await waitForHydration(page, `#settings-section-${mode}-consumption-export`);
  await page.evaluate(() => document.fonts.ready);
  await expect(section(page, mode).getByRole('listitem')).toHaveCount(5);
  await expect(section(page, mode)).not.toContainText(/settings\.(?:user|admin)\.export\./);
}
async function presentation(page: Page, desktop: boolean, mode: 'user' | 'admin' = 'user') {
  const group = section(page, mode).getByRole('group', {
    name: copy(`settings.${mode}.export.period_title`),
  });
  for (const kind of ['start', 'end']) {
    const control = group.getByLabel(copy(`settings.${mode}.export.${kind}_date`), { exact: true });
    const bounds = await box(control);
    const label = await box(group.locator(`label[for="${mode}-export-${kind}-date"]`));
    expect(Math.abs(bounds.y + bounds.height / 2 - label.y - label.height / 2)).toBeLessThan(2);
  }
  for (let index = 0; index < TYPES.length; index++) {
    const item = row(page, index, mode);
    const title = await box(item.getByRole('heading'));
    const action = await box(button(page, index, mode));
    const description = await box(
      item.getByText(copy(`settings.${mode}.export.${KEYS[index]}_description`), { exact: true })
    );
    if (desktop) {
      expect(Math.abs(title.y + title.height / 2 - action.y - action.height / 2)).toBeLessThan(3);
      expect(Math.abs(description.x - title.x)).toBeLessThan(2);
    } else {
      expect(description.width).toBeGreaterThan((await box(item)).width - 40);
      expect(action.y).toBeGreaterThanOrEqual(description.y + description.height);
      expect(action.height).toBeGreaterThanOrEqual(44);
    }
    expect(description.y).toBeGreaterThanOrEqual(title.y + title.height);
  }
  if (desktop) {
    const presets = await Promise.all(
      ['current_month', 'last_month', 'last_30_days', 'all_time'].map(key =>
        box(
          group.getByRole('button', {
            name: copy(`settings.${mode}.export.preset_${key}`),
            exact: true,
          })
        )
      )
    );
    for (const preset of presets) expect(Math.abs(preset.y - presets[0].y)).toBeLessThan(2);
  }
  await expectNoOverflow(page, `consumption exports ${mode} ${desktop ? 'desktop' : 'mobile'}`);
}
async function capture(page: Page, info: TestInfo, name: string) {
  const file = info.outputPath(`${name}.png`);
  await page.screenshot({ path: file, fullPage: true });
  await info.attach(name, { path: file, contentType: 'image/png' });
}
const observations = new WeakMap<Page, { api: string[]; errors: string[]; google: string[] }>();
test.beforeEach(async ({ page, context, mockApi, baseURL }) => {
  if (baseURL)
    await context.addCookies([
      {
        name: 'lia_session',
        value: 'e2e-session',
        url: new URL(baseURL).origin,
        httpOnly: true,
        sameSite: 'Lax',
      },
    ]);
  await page.addInitScript(() =>
    localStorage.setItem(
      'lia_eyes_widget_prefs',
      JSON.stringify({ state: { visible: false }, version: 0 })
    )
  );
  await mockApi([
    { url: '**/api/v1/notifications/broadcasts/unread', method: 'GET', json: { broadcasts: [] } },
    { url: '**/api/v1/agents/runs/active', method: 'GET', json: { active: false } },
    {
      url: '**/api/v1/system-settings/debug-panel-status',
      method: 'GET',
      json: { enabled: false, user_access_available: false },
    },
    {
      url: '**/api/v1/habits/presence',
      method: 'POST',
      handler: route => route.fulfill({ status: 204, body: '' }),
    },
    idleNotificationStream,
  ]);
  const observed = { api: [] as string[], errors: [] as string[], google: [] as string[] };
  observations.set(page, observed);
  page.on('response', response => {
    if (response.status() === 501 && new URL(response.url()).pathname.startsWith('/api/v1/'))
      observed.api.push(response.url());
  });
  page.on('pageerror', error => observed.errors.push(error.message));
  context.on('request', request => {
    if (
      ['www.google.com', 'content-autofill.googleapis.com'].includes(
        new URL(request.url()).hostname
      )
    )
      observed.google.push(request.url());
  });
});
test.afterEach(async ({ page, apiNetworkGuard }, info) => {
  const observed = observations.get(page)!;
  await info.attach('network-isolation.json', {
    body: JSON.stringify(
      { ...observed, blockedTransport: apiNetworkGuard.blockedRequests },
      null,
      2
    ),
    contentType: 'application/json',
  });
  expect(observed.api, 'every actual API operation is explicitly mocked').toEqual([]);
  expect(observed.errors, 'no uncaught page errors').toEqual([]);
  expect(
    observed.google,
    'Google services never originate from application pages or workers'
  ).toEqual([]);
  // These opaque browser services remain DENIED by the unchanged transport guard.
  const browserRefusals = new Set([
    'CONNECT www.google.com:443',
    'CONNECT content-autofill.googleapis.com:443',
  ]);
  expect(apiNetworkGuard.blockedRequests.filter(request => !browserRefusals.has(request))).toEqual(
    []
  );
});

test('1440px light: five real CSV downloads, dates, native filenames and aligned collection', async ({
  page,
  authenticate,
  mockApi,
  browserName,
}, info) => {
  await page.setViewportSize({ width: 1440, height: 1050 });
  await prepareTheme(page, 'light');
  await authenticate({ language: 'fr', theme: 'light' });
  const requests: string[] = [];
  await mockApi(
    TYPES.map(type => ({
      url: `**/api/v1/usage/export/${type}*`,
      method: 'GET',
      handler: async route => {
        await expectSessionCookie(route.request(), browserName, 'lia_session=e2e-session');
        const url = new URL(route.request().url());
        expect(url.searchParams.get('start_date')).toBe('2026-10-01');
        expect(url.searchParams.get('end_date')).toBe('2026-10-15');
        expect(url.searchParams.has('user_id')).toBe(false);
        requests.push(type);
        await route.fulfill({
          contentType: 'text/csv',
          headers: { 'Content-Disposition': `attachment; filename="${type}_2026-10.csv"` },
          body: CSV,
        });
      },
    }))
  );
  await open(page);
  await presentation(page, true);
  await expect(section(page).getByRole('combobox')).toHaveCount(0);
  await section(page)
    .getByLabel(copy('settings.user.export.start_date'), { exact: true })
    .fill('2026-10-15');
  await section(page)
    .getByLabel(copy('settings.user.export.end_date'), { exact: true })
    .fill('2026-10-01');
  await expect(section(page).getByRole('alert')).toHaveText(
    copy('settings.user.export.invalid_period')
  );
  await expect(button(page, 0)).toBeDisabled();
  expect(requests).toEqual([]);
  await section(page)
    .getByLabel(copy('settings.user.export.start_date'), { exact: true })
    .fill('2026-10-01');
  await section(page)
    .getByLabel(copy('settings.user.export.end_date'), { exact: true })
    .fill('2026-10-15');
  await capture(page, info, 'consumption-export-desktop-light');
  for (let index = 0; index < TYPES.length; index++) {
    const waiting = page.waitForEvent('download');
    await button(page, index).click();
    const download = await waiting;
    expect(download.suggestedFilename()).toBe(`${TYPES[index]}_2026-10.csv`);
    const file = await download.path();
    expect(file).not.toBeNull();
    expect(readFileSync(file!, 'utf8')).toBe(CSV);
    await expect(button(page, index)).toBeEnabled();
  }
  expect(requests).toEqual(TYPES);
  const scan = await scanPage(page, info, 'consumption export desktop');
  expect(scan.blocking, scan.summary).toEqual([]);
});

test('320px OLED: readable admin filters, keyboard autocomplete, failed CSV then deliberate retry', async ({
  page,
  authenticate,
  mockApi,
  browserName,
}, info) => {
  await page.setViewportSize({ width: 320, height: 860 });
  await prepareTheme(page, 'oled');
  await authenticate({ language: 'fr', theme: 'oled', font_size: 20, is_superuser: true });
  let exports = 0;
  await mockApi([
    {
      url: '**/api/v1/users/admin/autocomplete*',
      method: 'GET',
      handler: async route => {
        expect(new URL(route.request().url()).searchParams.get('q')).toBe('alice');
        await route.fulfill({
          json: {
            users: [
              {
                id: '00000000-0000-4000-8000-000000000701',
                email: 'alice@example.test',
                full_name: 'Alice Exemple',
                is_active: true,
              },
            ],
          },
        });
      },
    },
    {
      url: '**/api/v1/admin/google-api/export/token-usage*',
      method: 'GET',
      handler: async route => {
        await expectSessionCookie(route.request(), browserName, 'lia_session=e2e-session');
        exports += 1;
        const url = new URL(route.request().url());
        expect(url.searchParams.get('user_id')).toBe('00000000-0000-4000-8000-000000000701');
        expect(url.searchParams.has('start_date')).toBe(false);
        if (exports === 1) {
          await route.fulfill({ status: 503, json: { detail: 'temporarily unavailable' } });
          return;
        }
        await route.fulfill({
          contentType: 'text/csv',
          headers: { 'Content-Disposition': 'attachment; filename="alice_usage.csv"' },
          body: CSV,
        });
      },
    },
  ]);
  await open(page, 'admin');
  await presentation(page, false, 'admin');
  await capture(page, info, 'consumption-export-mobile-oled');
  const search = section(page, 'admin').getByRole('combobox');
  await search.fill('alice');
  await expect(section(page, 'admin').getByRole('option')).toHaveCount(1);
  await search.press('ArrowDown');
  await search.press('Enter');
  await expect(section(page, 'admin').getByRole('listbox')).toHaveCount(0);
  await button(page, 0, 'admin').click();
  await expect(section(page, 'admin').getByRole('alert')).toHaveText(
    copy('settings.admin.export.error')
  );
  expect(exports).toBe(1);
  const waiting = page.waitForEvent('download');
  await button(page, 0, 'admin').click();
  expect((await waiting).suggestedFilename()).toBe('alice_usage.csv');
  await expect(section(page, 'admin').getByRole('alert')).toHaveCount(0);
  expect(exports).toBe(2);
  await section(page, 'admin')
    .getByRole('button', { name: copy('settings.admin.export.clear_user'), exact: true })
    .click();
  await expect(search).toBeFocused();
  await expectNoOverflow(page, 'admin export after CSV retry');
  const scan = await scanPage(page, info, 'consumption export mobile OLED');
  expect(scan.blocking, scan.summary).toEqual([]);
});

test('a normal account cannot mount the administrator export through a crafted deep link', async ({
  page,
  authenticate,
}) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await prepareTheme(page, 'light');
  await authenticate({ language: 'fr', is_superuser: false });
  const response = await page.goto('/fr/dashboard/settings?section=admin-consumption-export');
  expect(response?.status()).toBe(200);
  await waitForHydration(page, 'main');
  await expect(page.locator('#settings-section-admin-consumption-export')).toHaveCount(0);
  await expect(
    page.getByRole('combobox', { name: copy('settings.admin.export.user_filter'), exact: true })
  ).toHaveCount(0);
});
