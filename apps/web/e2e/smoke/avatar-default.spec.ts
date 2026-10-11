/** The landing has a fixed identity; one persistent companion follows the device in the app. */
import type { Page } from '@playwright/test';
import {
  test,
  expect,
  chatRoutes,
  briefingCardsMock,
  waitForHydration,
  type MockRoute,
} from '../fixtures';
import en from '../../locales/en/translation.json';

const PREFS_KEY = 'lia_eyes_widget_prefs';
const savedPreference = (style: 'cozmo' | 'moss') =>
  JSON.stringify({
    state: { visible: true, style, size: 'md', position: null, landingPosition: null },
    version: 0,
  });

const applicationRoutes: MockRoute[] = [
  ...chatRoutes([]),
  briefingCardsMock,
  {
    url: '**/api/v1/briefing/synthesis',
    json: { greeting: { text: 'Welcome back', generated_at: null, usage: null }, synthesis: null },
  },
  { url: '**/api/v1/briefing/companion-context', json: { timezone: 'UTC', weather: null } },
  { url: /\/api\/v1\/connectors(?:\?fresh=true)?$/, json: { connectors: [] } },
  { url: '**/api/v1/scheduled-actions**', json: { actions: [], total: 0 } },
  { url: '**/api/v1/usage/**', json: {} },
];

async function prepareDevice(
  page: Page,
  baseURL: string | undefined,
  variant: 'male' | 'female',
  preferences: string | null = null
) {
  if (!baseURL) throw new Error('The hermetic app origin is required');
  await page.context().addCookies([{ name: 'lia_gender', value: variant, url: baseURL }]);
  await page.addInitScript(
    ({ key, preferences }) => {
      if (preferences === null) localStorage.removeItem(key);
      else localStorage.setItem(key, preferences);
    },
    { key: PREFS_KEY, preferences }
  );
}

test.use({ viewport: { width: 1280, height: 900 }, reducedMotion: 'reduce' });

test('a first visit to the landing shows male Bip in extra large', async ({ page, baseURL }) => {
  await prepareDevice(page, baseURL, 'female');
  await page.goto('/en');
  const widget = page.locator('.lia-eyes-widget');
  const identity = widget.locator('[data-character="bip"][data-spirit-companion="male"]');
  const face = identity.locator('.lia-eyes[data-style="billes"]');
  await expect(widget).toHaveCount(1);
  await expect(face).toBeVisible();
  await expect(face).toHaveClass(/lia-eyes--xl/);
  await expect(face).toHaveCSS('font-size', '64px');
  await expect(widget.getByRole('button', { name: en.eyes.cycle_size })).toHaveCount(0);
  expect((await page.context().cookies()).find(cookie => cookie.name === 'lia_gender')?.value).toBe(
    'female'
  );
});

test('the fixed landing identity preserves a saved Cozmo size and female preference', async ({
  page,
  baseURL,
}) => {
  const preferences = savedPreference('cozmo');
  await prepareDevice(page, baseURL, 'female', preferences);
  await page.goto('/en');
  const widget = page.locator('.lia-eyes-widget');
  const face = widget.locator(
    '[data-character="bip"][data-spirit-companion="male"] .lia-eyes[data-style="billes"]'
  );
  await expect(widget).toHaveCount(1);
  await expect(face).toBeVisible();
  await expect(face).toHaveClass(/lia-eyes--xl/);
  await expect(face).toHaveCSS('font-size', '64px');
  await expect(widget.getByRole('button', { name: en.eyes.cycle_size })).toHaveCount(0);
  expect(await page.evaluate(key => localStorage.getItem(key), PREFS_KEY)).toBe(preferences);
  expect((await page.context().cookies()).find(cookie => cookie.name === 'lia_gender')?.value).toBe(
    'female'
  );
});

for (const device of [
  { name: 'default male Bip XL', character: 'bip', size: 'xl', variant: 'male', preferences: null },
  {
    name: 'default female Bip XL',
    character: 'bip',
    size: 'xl',
    variant: 'female',
    preferences: null,
  },
  {
    name: 'saved female Mousse MD',
    character: 'moss',
    size: 'md',
    variant: 'female',
    preferences: savedPreference('moss'),
  },
] as const) {
  test(`${device.name} keeps the same widget through chat, settings, home and FAQ`, async ({
    page,
    baseURL,
    authenticate,
    mockApi,
  }) => {
    await prepareDevice(page, baseURL, device.variant, device.preferences);
    await authenticate({ language: 'en' });
    await mockApi(applicationRoutes);
    await page.goto('/en/dashboard/chat');
    const widget = page.locator('.lia-eyes-widget');
    const identity = widget.locator(
      `[data-character="${device.character}"][data-spirit-companion="${device.variant}"]`
    );
    const face = identity.locator('.lia-eyes[data-style="billes"]');
    await expect(widget).toHaveCount(1);
    await expect(face).toBeVisible();
    await expect(face).toHaveClass(new RegExp(`lia-eyes--${device.size}`));
    await expect
      .poll(() => face.evaluate(node => node.getBoundingClientRect().width))
      .toBeCloseTo(device.size === 'xl' ? 166.4 : 78, 1);
    await waitForHydration(page, '.lia-eyes-widget');
    const originalWidget = await widget.elementHandle();
    const originalFace = await face.elementHandle();
    if (!originalWidget || !originalFace) throw new Error('The mounted companion is required');
    const preferences = await page.evaluate(key => localStorage.getItem(key), PREFS_KEY);
    const gender = (await page.context().cookies()).find(cookie => cookie.name === 'lia_gender');
    const navigation = page.locator('header nav');

    for (const [label, route] of [
      [en.navigation.settings, '/en/dashboard/settings'],
      [en.navigation.dashboard, '/en/dashboard'],
      [en.navigation.faq, '/en/dashboard/faq'],
      [en.navigation.chat, '/en/dashboard/chat'],
    ] as const) {
      await navigation.getByRole('link', { name: label, exact: true }).click();
      await expect(page).toHaveURL(url => url.pathname === route);
      await expect(navigation.getByRole('link', { name: label, exact: true })).toHaveAttribute(
        'aria-current',
        'page'
      );
      await expect(widget).toHaveCount(1);
      await expect(face).toBeVisible();
      await expect(face).toHaveClass(new RegExp(`lia-eyes--${device.size}`));
      await expect
        .poll(() => face.evaluate(node => node.getBoundingClientRect().width))
        .toBeCloseTo(device.size === 'xl' ? 166.4 : 78, 1);
      expect(await widget.evaluate((node, previous) => node === previous, originalWidget)).toBe(
        true
      );
      expect(await face.evaluate((node, previous) => node === previous, originalFace)).toBe(true);
      expect(await page.evaluate(key => localStorage.getItem(key), PREFS_KEY)).toBe(preferences);
      expect((await page.context().cookies()).find(cookie => cookie.name === 'lia_gender')).toEqual(
        gender
      );
    }
    await originalWidget.dispose();
    await originalFace.dispose();
  });
}
