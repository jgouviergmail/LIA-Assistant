/**
 * Mobile navigation through the logo (A2).
 *
 * Below `md` the header's `<nav>` is hidden. Until now nothing replaced it: on
 * a phone, from the chat, the dashboard was reachable through the logo and no
 * other page at all — settings and help required typing a URL.
 *
 * Only a browser can prove this, because the whole defect lives in a media
 * query: a component test renders both forms at once and sees nothing wrong.
 * What is asserted here is the exclusivity (exactly one logo affordance at any
 * width) and the journey (open the menu, land on the page).
 */
import { test, expect, type MockRoute } from '../fixtures';

const ROUTES: MockRoute[] = [
  { url: '**/api/v1/briefing/cards', json: { cards: {} } },
  {
    url: '**/api/v1/briefing/synthesis',
    json: { greeting: 'Bonjour', synthesis: null, generated_at: null, llm_usage: null },
  },
  { url: '**/api/v1/usage/**', json: {} },
];

const PHONE = { width: 390, height: 800 };
const DESKTOP = { width: 1280, height: 900 };

test.describe('mobile navigation', () => {
  test('the logo opens every destination on a phone', async ({ page, authenticate, mockApi }) => {
    await authenticate({ language: 'fr' });
    await mockApi(ROUTES);
    await page.setViewportSize(PHONE);
    await page.goto('/fr/dashboard/chat');

    const trigger = page.getByRole('button', { name: 'Menu' });
    await expect(trigger, 'the logo must be an entry point on a phone').toBeVisible({
      timeout: 30_000,
    });
    await trigger.click();

    // The four destinations of the desktop nav, none missing.
    const items = page.getByRole('menuitem');
    await expect(items).toHaveCount(4);

    // And the journey actually completes.
    await page.getByRole('menuitem', { name: /Réglages/i }).click();
    await page.waitForURL(/\/dashboard\/settings/, { timeout: 30_000 });
  });

  test('the desktop keeps its plain link, and no menu', async ({ page, authenticate, mockApi }) => {
    // A menu on desktop would duplicate the visible nav and steal the "go
    // home" gesture the logo has always been.
    await authenticate({ language: 'fr' });
    await mockApi(ROUTES);
    await page.setViewportSize(DESKTOP);
    await page.goto('/fr/dashboard/chat');

    await expect(page.getByRole('navigation')).toBeVisible({ timeout: 30_000 });
    // Both forms exist in the DOM (Tailwind hides one with `display`), so the
    // assertion is on VISIBILITY, not on presence.
    await expect(page.getByRole('button', { name: 'Menu' })).toBeHidden();
    await expect(page.locator('header a').filter({ hasText: 'LIA' }).first()).toBeVisible();
  });

  test('exactly one logo affordance exists at any width', async ({
    page,
    authenticate,
    mockApi,
  }) => {
    // The two forms are mounted exclusively; both showing would put two
    // "LIA" controls side by side in a header that already clips below 380 px.
    await authenticate({ language: 'fr' });
    await mockApi(ROUTES);
    await page.goto('/fr/dashboard');

    // Addressed explicitly rather than by their shared "LIA" text: both are
    // mounted at every width, so the assertion is which ONE is displayed.
    const menuButton = page.getByRole('button', { name: 'Menu' });
    const homeLink = page.locator('header a').filter({ hasText: 'LIA' }).first();

    for (const { width, height, expectMenu } of [
      { width: 320, height: 640, expectMenu: true },
      { ...PHONE, expectMenu: true },
      { width: 767, height: 900, expectMenu: true },
      { width: 768, height: 900, expectMenu: false },
      { ...DESKTOP, expectMenu: false },
    ]) {
      await page.setViewportSize({ width, height });
      await expect(menuButton, `${width}px: menu button`).toBeVisible({ visible: expectMenu });
      await expect(homeLink, `${width}px: home link`).toBeVisible({ visible: !expectMenu });
    }
  });
});
