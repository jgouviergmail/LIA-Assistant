/** The public landing has a fixed identity; a new chat follows the device default. */
import { test, expect, chatRoutes } from '../fixtures';

test('a first visit to the landing shows a small Smiley even on desktop', async ({ page }) => {
  await page.goto('/en');
  const avatar = page.locator('.lia-eyes[data-style="smiley"]');
  await expect(avatar).toBeVisible();
  await expect(avatar).toHaveClass(/lia-eyes--sm/);
});

test('the public landing shows Smiley even when another chat style was saved', async ({ page }) => {
  await page.addInitScript(() => {
    localStorage.setItem(
      'lia_eyes_widget_prefs',
      JSON.stringify({ state: { visible: true, style: 'cozmo', size: 'md' }, version: 0 })
    );
  });
  await page.goto('/en');
  const avatar = page.locator('.lia-eyes[data-style="smiley"]');
  await expect(avatar).toBeVisible();
  await expect(avatar).toHaveClass(/lia-eyes--md/);
  expect(
    await page.evaluate(() => JSON.parse(localStorage.getItem('lia_eyes_widget_prefs')!).state.style)
  ).toBe('cozmo');
});

test('a new chat without an avatar preference starts with Smiley', async ({
  page,
  authenticate,
  mockApi,
}) => {
  await authenticate();
  await mockApi(chatRoutes([]));
  await page.goto('/en/dashboard/chat');
  await expect(page.locator('.lia-eyes[data-style="smiley"]').last()).toBeVisible();
});
