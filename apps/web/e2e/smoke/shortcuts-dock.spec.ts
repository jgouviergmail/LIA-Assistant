/**
 * The shortcuts dock (ADR-277) — the pinned settings sections on every
 * dashboard screen, and the picker that pins them.
 *
 * Hermetic: `/auth/me` carries the pinned list (the dock reads it from the
 * signed-in user, never from a request of its own), the picker's GET and PUT
 * are mocked, everything else dies on the 501 catch-all. Proves in a real
 * browser what jsdom cannot: the capsule is visible and named, its links
 * navigate to the section deep link and survive the navigation (it is the
 * layout's, not the page's), it folds into a restore button and unfolds, the
 * picker sends the WHOLE list on a single check, and axe finds nothing
 * blocking around it.
 */
import { scanPage } from '../a11y/scan';
import { test, expect } from '../fixtures';

const ENDPOINT = '**/api/v1/users/me/settings-shortcuts';
const DOCK_NAME = /raccourcis/i;

test.describe('the shortcuts dock', () => {
  test('shows the pinned sections, named, and opens one', async ({
    page,
    authenticate,
    mockApi,
  }, testInfo) => {
    await authenticate({ language: 'fr', settings_shortcuts: ['theme', 'font'] });
    await mockApi([
      { url: ENDPOINT, method: 'GET', json: { shortcuts: ['theme', 'font'], max_count: 5 } },
    ]);
    await page.goto('/fr/dashboard/settings');

    const dock = page.getByRole('navigation', { name: DOCK_NAME });
    await expect(dock).toBeVisible();
    const links = dock.getByRole('link');
    await expect(links).toHaveCount(2);
    // Named after the section, for a reader who cannot see the icon.
    await expect(links.first()).toHaveAccessibleName('Apparence');
    await expect(links.nth(1)).toHaveAccessibleName('Police');
    await scanPage(page, testInfo, 'shortcuts-dock');

    await links.first().click();
    await expect(page).toHaveURL(/section=theme/);
    // Still there after the navigation: the dock belongs to the layout.
    await expect(page.getByRole('navigation', { name: DOCK_NAME })).toBeVisible();
  });

  test('folds into a restore button and unfolds', async ({ page, authenticate }, testInfo) => {
    await authenticate({ language: 'fr', settings_shortcuts: ['theme'] });
    await page.goto('/fr/dashboard/settings');
    const dock = page.getByRole('navigation', { name: DOCK_NAME });
    await expect(dock).toBeVisible();

    await dock.getByRole('button', { name: 'Réduire les raccourcis' }).click();

    await expect(dock).toBeHidden();
    const restore = page.getByRole('button', { name: 'Afficher les raccourcis' });
    await expect(restore).toBeVisible();
    await scanPage(page, testInfo, 'shortcuts-dock-folded');

    await restore.click();

    await expect(page.getByRole('navigation', { name: DOCK_NAME })).toBeVisible();
  });

  test('unfolds upward from the bottom of the screen, never off it', async ({
    page,
    authenticate,
  }) => {
    // The device remembers a folded dock parked near the bottom edge.
    await page.addInitScript(() => {
      localStorage.setItem(
        'lia_shortcuts_dock_prefs',
        JSON.stringify({ state: { position: { xPct: 90, yPct: 88 }, minimized: true }, version: 0 })
      );
    });
    await authenticate({ language: 'fr', settings_shortcuts: ['theme', 'font', 'notifications'] });
    await page.goto('/fr/dashboard/settings');
    const button = page.getByRole('button', { name: 'Afficher les raccourcis' });
    const folded = await button.boundingBox();
    expect(folded).not.toBeNull();

    await button.click();

    const capsule = await page.getByRole('navigation', { name: DOCK_NAME }).boundingBox();
    const viewport = page.viewportSize();
    expect(capsule).not.toBeNull();
    expect(viewport).not.toBeNull();
    // Its foot is where the button's foot was, and it grew UP from there.
    expect(Math.abs(capsule!.y + capsule!.height - (folded!.y + folded!.height))).toBeLessThan(2);
    expect(capsule!.y).toBeGreaterThanOrEqual(0);
    expect(capsule!.y + capsule!.height).toBeLessThanOrEqual(viewport!.height);
  });

  test('is absent while nothing is pinned', async ({ page, authenticate }) => {
    await authenticate({ language: 'fr' });
    await page.goto('/fr/dashboard/settings');
    await expect(page.getByRole('main')).toBeVisible();
    // A negative right after load could pass before hydration: give the
    // shell the time the capture specs give it.
    await page.waitForTimeout(1000);

    await expect(page.getByRole('navigation', { name: DOCK_NAME })).toHaveCount(0);
  });

  test('the picker pins a section by sending the whole list', async ({
    page,
    authenticate,
    mockApi,
  }) => {
    await authenticate({ language: 'fr', settings_shortcuts: ['theme'] });
    await mockApi([
      { url: ENDPOINT, method: 'GET', json: { shortcuts: ['theme'], max_count: 5 } },
      { url: ENDPOINT, method: 'PUT', json: { shortcuts: ['theme', 'font'], max_count: 5 } },
    ]);
    await page.goto('/fr/dashboard/settings?section=my-shortcuts');

    const police = page.getByRole('checkbox', { name: 'Police' });
    await expect(police).toBeVisible();
    await expect(page.getByRole('checkbox', { name: 'Apparence' })).toBeChecked();
    // The picker never offers itself.
    await expect(page.getByRole('checkbox', { name: 'Mes raccourcis' })).toHaveCount(0);

    const put = page.waitForRequest(
      request =>
        request.method() === 'PUT' && request.url().includes('/users/me/settings-shortcuts')
    );
    await police.check();

    expect((await put).postDataJSON()).toEqual({ shortcuts: ['theme', 'font'] });
    await expect(police).toBeChecked();
  });
});
