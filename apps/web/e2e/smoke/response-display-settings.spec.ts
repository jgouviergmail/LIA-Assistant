/** Display modes: focused real-browser layout, autosave and recovery proof. */
import { readFileSync } from 'node:fs';
import path from 'node:path';
import type { Locator, Page, TestInfo } from '@playwright/test';
import {
  test,
  expect,
  waitForHydration,
  waitForMockGate,
  idleNotificationStream,
} from '../fixtures';
import { scanPage } from '../a11y/scan';
import { expectNoOverflow, prepareTheme } from './overflow-report';

const MODES = ['cards', 'html', 'html_cards', 'markdown'] as const;
type DisplayMode = (typeof MODES)[number];
const PREFIX = 'settings.preferences.display_mode';

function copy(key: string): string {
  let value: unknown = JSON.parse(
    readFileSync(path.join(__dirname, '../../locales/fr/translation.json'), 'utf8')
  );
  for (const part of key.split('.')) {
    if (!value || typeof value !== 'object') throw new Error(`Missing French label: ${key}`);
    value = (value as Record<string, unknown>)[part];
  }
  if (typeof value !== 'string') throw new Error(`Missing French label: ${key}`);
  return value;
}

function settings(page: Page): Locator {
  return page.locator('#settings-section-display-mode');
}

function option(page: Page, mode: DisplayMode): Locator {
  return settings(page).getByRole('button', {
    name: copy(`${PREFIX}.modes.${mode}.label`),
    exact: true,
  });
}

function preview(page: Page): Locator {
  return settings(page).getByRole('region', { name: copy(`${PREFIX}.preview.title`), exact: true });
}

async function ready(page: Page): Promise<void> {
  const response = await page.goto('/fr/dashboard/settings?section=display-mode');
  expect(response?.status(), 'the real settings document must load').toBe(200);
  await waitForHydration(page, '#settings-section-display-mode button[aria-pressed]');
  await expect(option(page, 'cards')).toBeVisible();
  await page.waitForFunction(
    () =>
      getComputedStyle(document.documentElement).getPropertyValue('--color-background').trim() !==
      ''
  );
  await page.evaluate(() => document.fonts.ready);
}

async function measured(locator: Locator) {
  const box = await locator.boundingBox();
  expect(box, 'a visible element must have a measured box').not.toBeNull();
  return box!;
}

async function layout(page: Page, desktop: boolean): Promise<void> {
  const boxes = await Promise.all(MODES.map(mode => measured(option(page, mode))));
  for (const [index, box] of boxes.entries()) {
    expect(Math.abs(box.x - boxes[0].x), 'display choices share the same left edge').toBeLessThan(
      2
    );
    expect(
      Math.abs(box.width - boxes[0].width),
      'display choices have consistent widths'
    ).toBeLessThan(2);
    expect(box.height, 'each choice remains an accessible touch target').toBeGreaterThanOrEqual(44);
    if (index > 0)
      expect(box.y).toBeGreaterThanOrEqual(boxes[index - 1].y + boxes[index - 1].height);
    expect(
      await option(page, MODES[index]).evaluate(
        element => element.scrollWidth <= element.clientWidth + 1
      ),
      'mode names and descriptions remain readable inside their choice'
    ).toBe(true);
  }
  const example = await measured(preview(page));
  if (desktop) {
    expect(
      example.x,
      'the example follows the vertical selector in the right column'
    ).toBeGreaterThanOrEqual(boxes[0].x + boxes[0].width + 8);
  } else {
    expect(
      example.y,
      'on phones the example follows all four vertical choices'
    ).toBeGreaterThanOrEqual(boxes[3].y + boxes[3].height);
  }
  await expectNoOverflow(page, desktop ? 'desktop display modes' : 'mobile display modes');
}

async function assertMode(page: Page, mode: DisplayMode): Promise<void> {
  await expect(option(page, mode)).toHaveAttribute('aria-pressed', 'true');
  await expect(option(page, mode)).toHaveAttribute('aria-disabled', 'false');
  await expect(settings(page).locator('button[aria-pressed="true"]')).toHaveCount(1);
  await expect(
    settings(page).locator(
      'button[aria-pressed] svg.lucide-check, button[aria-pressed] svg.lucide-circle-check'
    )
  ).toHaveCount(0);
  const example = preview(page);
  for (const key of ['weather.location', 'meeting.name', 'meeting.time', 'meeting.location']) {
    await expect(
      example.getByText(copy(`${PREFIX}.preview.${key}`), { exact: true })
    ).toBeVisible();
  }
  await expect(example).toContainText(copy(`${PREFIX}.preview.weather.condition`));
  await expect(example).toContainText(/20\s?°C/);
  await expect(example.getByRole('article')).toHaveCount(
    mode === 'cards' || mode === 'html_cards' ? 2 : 0
  );
  await expect(settings(page).getByText(/HTML enrichi/)).toHaveCount(0);
}

async function capture(page: Page, info: TestInfo, label: string): Promise<void> {
  await expect(page.locator('[data-sonner-toast]')).toHaveCount(0);
  const file = info.outputPath(`${label}.png`);
  await settings(page).screenshot({ path: file });
  await info.attach(label, { path: file, contentType: 'image/png' });
}

const observations = new WeakMap<
  Page,
  { unexpectedApi: string[]; pageErrors: string[]; unexpectedGoogleContextRequests: string[] }
>();

test.beforeEach(async ({ page, context, mockApi }) => {
  // Use the existing reading preference so the floating avatar does not cover examples.
  await page.addInitScript(() => {
    localStorage.setItem(
      'lia_eyes_widget_prefs',
      JSON.stringify({ state: { visible: false }, version: 0 })
    );
  });
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
  const observed = {
    unexpectedApi: [] as string[],
    pageErrors: [] as string[],
    unexpectedGoogleContextRequests: [] as string[],
  };
  observations.set(page, observed);
  context.on('request', request => {
    const host = new URL(request.url()).hostname;
    if (host === 'www.google.com' || host === 'content-autofill.googleapis.com')
      observed.unexpectedGoogleContextRequests.push(request.url());
  });
  page.on('response', response => {
    if (response.status() === 501 && new URL(response.url()).pathname.startsWith('/api/v1/'))
      observed.unexpectedApi.push(response.url());
  });
  page.on('pageerror', error => observed.pageErrors.push(error.message));
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
  expect(observed.unexpectedApi, 'every backend read and write is explicitly mocked').toEqual([]);
  expect(observed.pageErrors, 'no uncaught application error occurred').toEqual([]);
  // Chrome's background search and form-autofill services attempt opaque tunnels.
  // Chromium declares AutofillServerCommunication in components/autofill/core/common/
  // autofill_features.cc. Neither host may originate from any application context page or worker;
  // the unchanged strict guard REFUSES both tunnels, never authorizes them.
  expect(
    observed.unexpectedGoogleContextRequests,
    'Google traffic cannot originate from any app context page or worker'
  ).toEqual([]);
  const browserOnlyRefusals = new Set([
    'CONNECT www.google.com:443',
    'CONNECT content-autofill.googleapis.com:443',
  ]);
  expect(
    apiNetworkGuard.blockedRequests.filter(request => !browserOnlyRefusals.has(request))
  ).toEqual([]);
});

test('1440px light: four faithful previews, keyboard autosave and guarded pending activation', async ({
  page,
  authenticate,
  mockApi,
}, info) => {
  await page.setViewportSize({ width: 1440, height: 1000 });
  await prepareTheme(page, 'light');
  const account = await authenticate({
    language: 'fr',
    response_display_mode: 'cards',
    theme: 'light',
  });
  let mode: DisplayMode = 'cards';
  const updates: unknown[] = [];
  let release: () => void = () => undefined;
  const firstSave = new Promise<void>(resolve => {
    release = resolve;
  });
  await mockApi([
    {
      url: '**/api/v1/auth/me',
      handler: route => route.fulfill({ json: { ...account, response_display_mode: mode } }),
    },
    {
      url: '**/api/v1/auth/me/display-mode-preference',
      method: 'PATCH',
      handler: async (route, signal) => {
        const body = route.request().postDataJSON() as { response_display_mode: DisplayMode };
        updates.push(body);
        if (updates.length === 1 && !(await waitForMockGate(firstSave, signal))) return;
        mode = body.response_display_mode;
        await route.fulfill({ json: { response_display_mode: mode } });
      },
    },
  ]);
  await ready(page);
  await assertMode(page, 'cards');
  await layout(page, true);
  await capture(page, info, 'display-cards-desktop-light-initial');
  const html = option(page, 'html');
  await html.focus();
  await page.keyboard.press('Enter');
  await expect.poll(() => updates.length).toBe(1);
  await expect(html).toHaveAttribute('aria-disabled', 'true');
  await page.keyboard.press('Enter');
  // Explicitly dispatch while aria-disabled: ordinary Playwright click waits for enabled.
  await option(page, 'markdown').click({ force: true });
  expect(updates).toEqual([{ response_display_mode: 'html' }]);
  await expect(option(page, 'cards')).toHaveAttribute('aria-pressed', 'true');
  // Focus must remain usable while the save is outstanding, including Tab.
  await html.focus();
  await page.keyboard.press('Tab');
  await expect(option(page, 'html_cards')).toBeFocused();
  await html.focus();
  release();
  await assertMode(page, 'html');
  await expect(html).toBeFocused();
  for (const next of ['html_cards', 'markdown', 'cards'] as const) {
    await option(page, next).focus();
    await page.keyboard.press('Enter');
    await assertMode(page, next);
    await expect(option(page, next)).toBeFocused();
    if (next === 'html_cards') await capture(page, info, 'display-html-cards-desktop-light');
  }
  expect(updates).toEqual(
    MODES.slice(1)
      .concat('cards')
      .map(response_display_mode => ({ response_display_mode }))
  );
  await option(page, 'cards').click();
  expect(updates).toHaveLength(4);
  await page.reload();
  await assertMode(page, 'cards');
  await layout(page, true);
  const audit = await scanPage(page, info, 'display-mode-desktop-light');
  expect(audit.blocking, audit.summary).toHaveLength(0);
});

test('320px light: one choice per row and failed autosave retries without false selection', async ({
  page,
  authenticate,
  mockApi,
}, info) => {
  await page.setViewportSize({ width: 320, height: 950 });
  await prepareTheme(page, 'light');
  const account = await authenticate({
    language: 'fr',
    response_display_mode: 'cards',
    theme: 'light',
  });
  let mode: DisplayMode = 'cards';
  const updates: unknown[] = [];
  await mockApi([
    {
      url: '**/api/v1/auth/me',
      handler: route => route.fulfill({ json: { ...account, response_display_mode: mode } }),
    },
    {
      url: '**/api/v1/auth/me/display-mode-preference',
      method: 'PATCH',
      handler: async route => {
        const body = route.request().postDataJSON() as { response_display_mode: DisplayMode };
        updates.push(body);
        if (updates.length === 1) {
          await route.fulfill({ status: 503, json: { detail: 'Temporarily unavailable' } });
          return;
        }
        mode = body.response_display_mode;
        await route.fulfill({ json: { response_display_mode: mode } });
      },
    },
  ]);
  await ready(page);
  await assertMode(page, 'cards');
  await layout(page, false);
  await option(page, 'html').click();
  await expect(page.getByText(copy('common.error'), { exact: true })).toBeVisible();
  await expect(option(page, 'html')).toHaveAttribute('aria-disabled', 'false');
  await assertMode(page, 'cards');
  await option(page, 'html').click();
  await assertMode(page, 'html');
  expect(updates).toEqual([{ response_display_mode: 'html' }, { response_display_mode: 'html' }]);
  await layout(page, false);
  await capture(page, info, 'display-html-mobile-320-light');
});

test('390px OLED and 20px text: every mode remains readable without selection checkmarks', async ({
  page,
  authenticate,
  mockApi,
}, info) => {
  await page.setViewportSize({ width: 390, height: 1050 });
  await prepareTheme(page, 'oled');
  const account = await authenticate({
    language: 'fr',
    response_display_mode: 'markdown',
    theme: 'oled',
    font_size: 20,
  });
  let mode: DisplayMode = 'markdown';
  await mockApi([
    {
      url: '**/api/v1/auth/me',
      handler: route => route.fulfill({ json: { ...account, response_display_mode: mode } }),
    },
    {
      url: '**/api/v1/auth/me/display-mode-preference',
      method: 'PATCH',
      handler: async route => {
        mode = (route.request().postDataJSON() as { response_display_mode: DisplayMode })
          .response_display_mode;
        await route.fulfill({ json: { response_display_mode: mode } });
      },
    },
  ]);
  await ready(page);
  await expect
    .poll(() =>
      settings(page)
        .getByRole('heading', { name: copy(`${PREFIX}.title`), exact: true })
        .evaluate(element => parseFloat(getComputedStyle(element).fontSize))
    )
    .toBe(20);
  for (const next of MODES) {
    await option(page, next).click();
    await assertMode(page, next);
    await layout(page, false);
  }
  await option(page, 'html_cards').click();
  await assertMode(page, 'html_cards');
  await capture(page, info, 'display-html-cards-mobile-oled-large-text');
  const audit = await scanPage(page, info, 'display-mode-mobile-oled-large-text');
  expect(audit.blocking, audit.summary).toHaveLength(0);
});
