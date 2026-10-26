/** Real guest bootstrap; intentionally never requests a world ticket or controller. */
import { test, expect } from './fixtures';
import fr from '../../locales/fr/translation.json';
import en from '../../locales/en/translation.json';
import { installOfflineFonts } from '../fixtures/offline-fonts';
import { worldProofUrl } from './world-route';

test.use({ locale: 'fr-FR' });

for (const [index, language, labels, nativeName] of [
  [1, 'fr', fr, 'Français'],
  [2, 'en', en, 'English'],
] as const) {
  test(
    'proof chooser: visitor ' + index + ' reaches their localized admission form',
    async ({ page, baseURL }, info) => {
      // Inherit the native suite's bounded budget, including cold Next dev compilation.
      if (!baseURL) throw new Error('Explicit disposable preview required');
      test.skip(
        worldProofUrl(baseURL, 'fr').pathname.endsWith('/dashboard/world'),
        'The identity chooser is development-only'
      );
      // Keep font downloads offline; dev WebSocket/bootstrap and all API calls stay real.
      await installOfflineFonts(page);
      if (index === 2) await page.setViewportSize({ width: 390, height: 844 });
      let sessions = 0;
      let tickets = 0;
      page.on('request', request => {
        if (request.method() !== 'POST') return;
        if (request.url().endsWith('/world-proof/session')) sessions++;
        if (request.url().endsWith('/world/ticket')) tickets++;
      });
      await page.goto(new URL('/world-preview?shared=1&resume=1', baseURL).href);
      const name =
        fr.world.session.proof_account.replace('{{index}}', String(index)) + ' · ' + nativeName;
      const [selected] = await Promise.all([
        page.waitForResponse(
          response =>
            response.request().method() === 'POST' &&
            response.url().endsWith('/world-proof/session')
        ),
        page.getByRole('button', { name, exact: true }).click(),
      ]);
      expect(selected.status()).toBe(200);
      await expect(page.locator('[data-world-public-name]')).toBeVisible();
      await expect(page.getByRole('textbox')).toHaveCount(0);
      await expect(
        page.getByRole('button', { name: labels.world.session.enter, exact: true })
      ).toBeVisible();
      await expect(page.locator('html')).toHaveAttribute('lang', language);
      await page.screenshot({ path: info.outputPath('localized-admission.png') });
      expect(sessions).toBe(1);
      expect(tickets).toBe(0);
      const cookies = await page.context().cookies(baseURL);
      expect(cookies.some(cookie => cookie.name === 'lia_session' && cookie.httpOnly)).toBe(true);
    }
  );
}
