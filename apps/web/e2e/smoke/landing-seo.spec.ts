/** Public URLs keep their language through hydration and contextual blog navigation. */
import { test, expect, waitForHydration } from '../fixtures';
import { awaitStyledPage, expectNoOverflow } from './overflow-report';
import fr from '../../locales/fr/translation.json';
import en from '../../locales/en/translation.json';
import de from '../../locales/de/translation.json';
import es from '../../locales/es/translation.json';
import it from '../../locales/it/translation.json';
import zh from '../../locales/zh/translation.json';

const CATALOGUES = { fr, en, de, es, it, zh };

test.describe('public SEO and translated reading journeys', () => {
  test.use({ locale: 'en-US', viewport: { width: 375, height: 812 } });

  for (const [language, catalogue] of Object.entries(CATALOGUES)) {
    test(`${language} keeps its URL language and follows a related article`, async ({
      page,
      context,
      baseURL,
      mockApi,
    }) => {
      if (!baseURL) throw new Error('The public journey requires a configured app URL');
      const prefix = language === 'fr' ? '' : `/${language}`;
      const savedLanguage = language === 'en' ? 'de' : 'en';
      // A different saved preference must neither redirect nor translate a public URL.
      await context.addCookies([{ name: 'NEXT_LOCALE', value: savedLanguage, url: baseURL }]);
      await mockApi([{ url: '**/api/v1/auth/me', status: 401, json: { detail: 'anonymous' } }]);

      await page.goto(prefix || '/');
      await waitForHydration(page, 'header nav');
      await awaitStyledPage(page, `${language} public introduction`);
      await expect(page.locator('html')).toHaveAttribute('lang', language);
      await expect(page).toHaveTitle(catalogue.landing.home_meta.title);
      await expect(page.locator('main h1')).toHaveCount(1);
      await expect(
        page.getByText(catalogue.landing.hero.subtitle_top, { exact: true })
      ).toBeVisible();
      await expect(
        page.getByText(catalogue.landing.hero.home_value, { exact: true })
      ).toBeVisible();
      await expectNoOverflow(page, `${language} introduction at 375px`);

      // The footer and list use Next Link: retain the shared layout across a
      // real client navigation before following the article's native HTML link.
      await page.locator(`footer a[href="${prefix}/blog"]`).click();
      await expect(page).toHaveURL(new URL(`${prefix}/blog`, baseURL).href);
      await expect(page.locator('html')).toHaveAttribute('lang', language);
      await page.locator(`main a[href="${prefix}/blog/google-workspace"]`).click();
      await expect(page).toHaveURL(new URL(`${prefix}/blog/google-workspace`, baseURL).href);
      await expect(page.locator('html')).toHaveAttribute('lang', language);
      await expect(page.locator('h1')).toHaveText(
        catalogue.blog.articles['google-workspace'].title
      );
      const related = page.locator('.blog-article-body a[href*="/blog/"]').first();
      await expect(related).toBeVisible();
      const href = await related.getAttribute('href');
      expect(href).toMatch(new RegExp(`^${prefix}/blog/[^/]+$`));
      if (!href) throw new Error('A contextual article link must have a destination');
      const slug = href.split('/').at(-1);
      const destination = Object.entries(catalogue.blog.articles).find(([key]) => key === slug);
      if (!destination) throw new Error(`Unknown related article: ${href}`);
      await related.click();
      await expect(page).toHaveURL(new URL(href, baseURL).href);
      await expect(page.locator('html')).toHaveAttribute('lang', language);
      await expect(page.locator('h1')).toHaveText(destination[1].title);
      expect((await context.cookies()).find(cookie => cookie.name === 'NEXT_LOCALE')?.value).toBe(
        savedLanguage
      );
    });
  }

  test('keeps an explicit French application visit through its unprefixed links', async ({
    page,
    context,
    baseURL,
    authenticate,
  }) => {
    if (!baseURL) throw new Error('The application journey requires a configured app URL');
    await page.setViewportSize({ width: 1280, height: 900 });
    await authenticate({ language: 'fr' });
    await context.addCookies([{ name: 'NEXT_LOCALE', value: 'en', url: baseURL }]);

    await page.goto('/fr/dashboard');
    await expect(page.getByRole('main')).toBeVisible();
    await expect(page.locator('html')).toHaveAttribute('lang', 'fr');
    await expect
      .poll(
        async () => (await context.cookies()).find(cookie => cookie.name === 'NEXT_LOCALE')?.value
      )
      .toBe('fr');
    await page.getByRole('link', { name: fr.navigation.settings, exact: true }).click();
    await expect(page).toHaveURL(new URL('/dashboard/settings', baseURL).href);
    await expect(page.locator('html')).toHaveAttribute('lang', 'fr');
    await expect(page.getByRole('combobox', { name: fr.settings.search.label })).toBeVisible();
  });

  test('confirms the visible French language before following a prefetched login link', async ({
    page,
    context,
    baseURL,
    mockApi,
  }) => {
    if (!baseURL) throw new Error('The language-choice journey requires a configured app URL');
    await page.setViewportSize({ width: 1280, height: 900 });
    await context.addCookies([{ name: 'NEXT_LOCALE', value: 'en', url: baseURL }]);
    await mockApi([{ url: '**/api/v1/auth/me', status: 401, json: { detail: 'anonymous' } }]);
    const prefetchedLogin = page.waitForResponse(response => {
      const url = new URL(response.url());
      return url.pathname === '/login' && url.searchParams.has('_rsc');
    });
    await page.goto('/');
    await waitForHydration(page, 'header nav');
    await prefetchedLogin;
    expect((await context.cookies()).find(cookie => cookie.name === 'NEXT_LOCALE')?.value).toBe(
      'en'
    );

    await page
      .getByRole('button', {
        name: fr.settings.language.selector_label.replace('{{name}}', 'Français'),
        exact: true,
      })
      .click();
    await page.getByRole('menuitem', { name: /^Français/ }).click();
    await expect
      .poll(
        async () => (await context.cookies()).find(cookie => cookie.name === 'NEXT_LOCALE')?.value
      )
      .toBe('fr');
    await page
      .getByRole('banner')
      .getByRole('link', { name: fr.landing.nav.login, exact: true })
      .click();
    await expect(page).toHaveURL(new URL('/login', baseURL).href);
    await expect(page.locator('html')).toHaveAttribute('lang', 'fr');
    await expect(page.locator('input[type="email"]')).toBeVisible();
  });
});
