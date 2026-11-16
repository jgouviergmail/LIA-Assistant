/** The maps' route stylesheet belongs to a visit, not every public page's navigation. */
import { test, expect, waitForHydration } from '../fixtures';

for (const scenario of [
  { name: 'landing header', path: '/', width: 1440, scope: 'header', control: '/blog' },
  { name: 'landing footer', path: '/', width: 1000, scope: 'footer', control: '/privacy' },
  {
    name: 'public footer',
    path: '/blog/react-execution-mode',
    width: 1000,
    scope: 'footer',
    control: '/privacy',
  },
]) {
  test(`${scenario.name} opens styled maps only after the reader follows the link`, async ({
    page,
    mockApi,
  }) => {
    await mockApi([{ url: '**/api/v1/auth/me', status: 401, json: { detail: 'anonymous' } }]);
    await page.setViewportSize({ width: scenario.width, height: 900 });
    const mapsPrefetches: string[] = [];
    page.on('request', request => {
      if (
        new URL(request.url()).pathname === '/maps' &&
        request.headers()['next-router-prefetch'] === '1'
      ) {
        mapsPrefetches.push(request.url());
      }
    });
    const neighbouringPrefetch = page.waitForResponse(response => {
      return (
        new URL(response.url()).pathname === scenario.control &&
        response.request().headers()['next-router-prefetch'] === '1'
      );
    });
    await page.goto(scenario.path);
    await waitForHydration(page, 'header nav');
    const link = page.locator(`${scenario.scope} a[href="/maps"]`).first();
    await link.scrollIntoViewIfNeeded();
    await neighbouringPrefetch;
    // Let the real Next prefetch queue drain: another link in the same visible
    // group must still prefetch, while maps must wait for navigation.
    await page.waitForLoadState('networkidle');
    expect(mapsPrefetches).toEqual([]);

    await link.click();
    await expect(page).toHaveURL(/\/maps$/);
    await expect(page.locator('main h1')).toBeVisible();
    // The scoped token comes from maps.css, not the shared public styles.
    await expect(page.locator('.lia-maps')).toHaveCSS('--lm-header', '4rem');
  });
}
