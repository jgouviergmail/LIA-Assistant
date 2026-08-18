/**
 * Visual review captures — a human-eye pass on the surfaces this cycle touched.
 *
 * NOT an assertion suite: `capture/**` is excluded from the default run
 * (`testIgnore` in the Playwright config), and exists so a reviewer can look
 * at what shipped instead of inferring it from the DOM. Run it explicitly
 * against a standalone build when a change is visual.
 */
import { test } from '../fixtures';

import { dashboardShellMocks } from '../fixtures/dashboard-shell';

const OUT = 'test-results/visual-review';

test.describe('visual review', () => {
  test('settings hub', async ({ page, authenticate, mockApi }) => {
    // The dashboard's theme is a stored user preference, not
    // `prefers-color-scheme`, so emulating the media query here would
    // capture the same picture twice. Both themes are covered where they
    // are actually switchable: the public axe scans.
    await authenticate({ language: 'fr' });
    await mockApi([
      ...dashboardShellMocks,
      { url: '**/api/v1/connectors', json: { connectors: [] } },
    ]);
    await page.setViewportSize({ width: 1440, height: 1000 });
    await page.goto('/fr/dashboard/settings');
    await page.getByRole('navigation', { name: 'Sections des réglages' }).waitFor({
      timeout: 60_000,
    });
    await page.waitForTimeout(1500);
    await page.screenshot({ path: `${OUT}/settings-hub.png`, fullPage: false });
  });
  test('settings rail on a phone', async ({ page, authenticate, mockApi }) => {
    await authenticate({ language: 'fr' });
    await mockApi(dashboardShellMocks);
    await page.setViewportSize({ width: 390, height: 844 });
    await page.goto('/fr/dashboard/settings');
    await page.getByRole('navigation', { name: 'Sections des réglages' }).waitFor({
      timeout: 60_000,
    });
    await page.waitForTimeout(1000);
    await page.screenshot({ path: `${OUT}/settings-rail-phone.png`, fullPage: false });
  });

  test('landing release band', async ({ page }) => {
    await page.setViewportSize({ width: 1440, height: 1000 });
    await page.goto('/fr#changelog');
    await page.waitForTimeout(2500);
    await page.locator('#changelog').scrollIntoViewIfNeeded();
    await page.waitForTimeout(1200);
    await page.locator('#changelog').screenshot({ path: `${OUT}/landing-changelog.png` });
  });

  test('more page — the new settings-shell card', async ({ page }) => {
    await page.setViewportSize({ width: 1280, height: 1000 });
    await page.goto('/fr/more#more-find');
    await page.waitForTimeout(2500);
    await page.locator('#more-find').scrollIntoViewIfNeeded();
    await page.waitForTimeout(2000);
    await page.locator('#more-find').screenshot({ path: `${OUT}/more-find-section.png` });
  });

  test('capability constellation', async ({ page, authenticate, mockApi }) => {
    await authenticate({ language: 'fr' });
    await mockApi([
      ...dashboardShellMocks,
      {
        url: '**/api/v1/capabilities',
        json: {
          nodes: [
            { key: 'connectors', active: true, detail: 4 },
            { key: 'memory', active: true, detail: 128 },
            { key: 'personality', active: true, detail: null },
            { key: 'voice', active: false, detail: null },
            { key: 'proactivity', active: true, detail: null },
            { key: 'images', active: true, detail: null },
            { key: 'documents', active: true, detail: null },
            { key: 'interests', active: true, detail: 7 },
            { key: 'routines', active: false, detail: 0 },
            { key: 'relations', active: true, detail: 3 },
            { key: 'habits', active: false, detail: 0 },
            { key: 'peers', active: true, detail: 2 },
            { key: 'channels', active: false, detail: 0 },
            { key: 'telephony', active: false, detail: 0 },
            { key: 'spaces', active: true, detail: 5 },
            { key: 'journals', active: true, detail: 42 },
            { key: 'skills', active: true, detail: 6 },
            { key: 'plugins', active: false, detail: 0 },
            { key: 'mcp_servers', active: true, detail: 2 },
          ],
          live: 12,
          total: 19,
        },
      },
    ]);
    await page.setViewportSize({ width: 1440, height: 1100 });
    await page.goto('/fr/dashboard/capabilities');
    await page.waitForTimeout(4000);
    await page.screenshot({ path: `${OUT}/capability-constellation.png`, fullPage: false });
  });
});
