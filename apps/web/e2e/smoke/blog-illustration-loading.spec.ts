/** Prefetch keeps route data warm without fetching illustrations from an unopened page. */
import { test, expect, waitForHydration } from '../fixtures';
import { awaitStyledPage } from './overflow-report';

const ARTICLE_PATH = '/blog/react-execution-mode';
const HERO_SELECTOR = 'main article img';
const HERO_PRELOAD =
  'head link[rel="preload"][as="image"][imagesrcset*="/articles/react-execution-mode-"][imagesizes="(max-width: 768px) 100vw, 768px"]';

test.describe('blog illustration loading', () => {
  test.beforeEach(async ({ mockApi }) => {
    await mockApi([{ url: '**/api/v1/auth/me', status: 401, json: { detail: 'anonymous' } }]);
  });

  for (const path of ['/blog', ARTICLE_PATH]) {
    test(`prefetching ${path} does not preload its illustrations on the landing`, async ({
      page,
    }) => {
      const prefetched = page.waitForResponse(response => {
        const url = new URL(response.url());
        return (
          url.pathname === path && response.request().headers()['next-router-prefetch'] === '1'
        );
      });
      await page.goto('/');
      await waitForHydration(page, 'header nav');
      if (path === ARTICLE_PATH) {
        await awaitStyledPage(page, 'landing article prefetch');
        const articleLink = page.locator(`main a[href="${path}"]`).first();
        await articleLink.scrollIntoViewIfNeeded();
        await expect(articleLink).toBeInViewport();
      }
      const response = await prefetched;
      expect(response.ok()).toBe(true);
      expect(response.headers()['content-type']).toContain('text/x-component');
      // Flight resource hints take effect as the prefetch is decoded, before
      // navigation. Images must stay with the route that actually draws them.
      const imageHints = (await response.text())
        .split('\n')
        .filter(line => line.startsWith(':HL') && line.includes(',"image",'));
      expect(imageHints).toEqual([]);
      await expect(page.locator('head link[rel="preload"][as="image"]')).toHaveCount(0);
      await expect(page).toHaveURL(/\/$/);
    });
  }

  test.describe('initial article HTML', () => {
    test.use({ javaScriptEnabled: false });

    for (const width of [390, 1440]) {
      test(`preloads the responsive hero before hydration at ${width}px`, async ({ page }) => {
        await page.setViewportSize({ width, height: 900 });
        await page.goto(ARTICLE_PATH);
        const hero = page.locator(HERO_SELECTOR);
        const preload = page.locator(HERO_PRELOAD);
        await expect(hero).toHaveAttribute('loading', 'eager');
        await expect(hero).toHaveAttribute('fetchpriority', 'high');
        await expect(preload).toHaveCount(1);
        await expect(preload).toHaveAttribute('imagesrcset', (await hero.getAttribute('srcset'))!);
        await expect(preload).toHaveAttribute('imagesizes', (await hero.getAttribute('sizes'))!);
        await expect(preload).toHaveAttribute('fetchpriority', 'high');
        await expect
          .poll(() => hero.evaluate((image: HTMLImageElement) => image.naturalWidth))
          .toBeGreaterThan(0);
      });
    }
  });

  test('loads the hero at high priority after a client navigation', async ({ page }) => {
    await page.goto('/blog');
    await waitForHydration(page, 'header nav');
    await page.locator(`main a[href="${ARTICLE_PATH}"]`).first().click();
    await expect(page).toHaveURL(new RegExp(`${ARTICLE_PATH}$`));
    const hero = page.locator(HERO_SELECTOR);
    await expect(hero).toHaveAttribute('loading', 'eager');
    await expect(hero).toHaveAttribute('fetchpriority', 'high');
    await expect(page.locator(HERO_PRELOAD)).toHaveCount(1);
    await expect
      .poll(() => hero.evaluate((image: HTMLImageElement) => image.naturalWidth))
      .toBeGreaterThan(0);
  });
});
