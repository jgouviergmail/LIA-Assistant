/**
 * Live-demonstrator invitation — what the instance offers, relayed with the
 * link (guided build, `task test:e2e:showroom`).
 *
 * What must hold:
 * - the page makes ONE request, the public link, and the demonstrator's
 *   capabilities travel with it — a second read to the demonstrator's origin
 *   is what the document's CSP refuses (measured here on 2026-09-12, the
 *   first version of this spec: the fetch was blocked and the lists never
 *   drew);
 * - the answer is drawn as two named lists under the locale's own labels, and
 *   they sit AFTER the limitations and BEFORE the call to action;
 * - a demonstrator the API could not read is said to have not answered — the
 *   "switched off" column is never left empty — and the link itself stays;
 * - the block has no blocking accessibility violation.
 */
import { expect, test, type Page } from '@playwright/test';

import { scanPage } from '../a11y/scan';

test.use({ locale: 'fr-FR' });

const DEMO_LINK = 'https://demo.example.test/register';

const DEMO_CAPABILITIES = {
  web_search: { enabled: true, family: 'reach' },
  bookmarks: { enabled: true, family: 'knowledge' },
  meetings: { enabled: false, family: 'media' },
  python_sandbox: { enabled: false, family: 'reach' },
};

/**
 * Publish a link, with or without the relayed block. Everything else under
 * /api/v1 is refused: the showroom oracle stays zero-API for the visitor
 * beyond this one read.
 */
async function installRoutes(
  page: Page,
  demoAnswered: boolean
): Promise<{ requests: () => { url: string; cookie: string | undefined }[] }> {
  const requests: { url: string; cookie: string | undefined }[] = [];
  await page.route('**/api/v1/**', async route => {
    const req = route.request();
    const url = req.url();
    requests.push({ url, cookie: req.headers()['cookie'] });
    if (url.endsWith('/api/v1/product/public-demo-link') && req.method() === 'GET') {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          enabled: true,
          url: DEMO_LINK,
          capabilities: demoAnswered ? DEMO_CAPABILITIES : null,
        }),
      });
      return;
    }
    await route.fulfill({ status: 501, body: `unexpected ${req.method()} ${url}` });
  });
  return { requests: () => requests };
}

test.describe('live-demonstrator invitation — capabilities relayed with the link', () => {
  test('draws the switched-on and switched-off lists from the relayed block', async ({
    page,
  }, testInfo) => {
    const { requests } = await installRoutes(page, true);
    await page.goto('/demo');

    const block = page.getByTestId('demo-capabilities');
    await expect(block).toBeVisible();

    // Under the locale's own labels, in the right column each.
    // `exact`: Playwright's name match is a substring by default, and
    // « Activé » is a substring of « Désactivé ».
    const on = block.getByRole('list', { name: 'Activé', exact: true });
    const off = block.getByRole('list', { name: 'Désactivé', exact: true });
    await expect(on.getByRole('listitem')).toHaveText(['Bookmarks', 'Recherche web']);
    await expect(off.getByRole('listitem')).toHaveText([
      'Enregistrement de réunions',
      'Python éphémère',
    ]);

    // ONE request, the link, without the visitor's cookies — and nothing to
    // the demonstrator's origin from the browser.
    const seen = requests();
    expect(seen.map(r => new URL(r.url).pathname)).toEqual(['/api/v1/product/public-demo-link']);
    expect(seen[0].cookie).toBeUndefined();

    // Order is the message: limitations, then the lists, then the door.
    const lastLimit = page.getByText(/une adresse e-mail valide/i).first();
    const cta = page.getByRole('link', { name: 'Ouvrir le démonstrateur' });
    const limitBox = await lastLimit.boundingBox();
    const blockBox = await block.boundingBox();
    const ctaBox = await cta.boundingBox();
    expect(limitBox!.y).toBeLessThan(blockBox!.y);
    expect(blockBox!.y).toBeLessThan(ctaBox!.y);

    await scanPage(page, testInfo, 'demo-invitation-capabilities');
  });

  test('says the demonstrator did not answer, and keeps the link', async ({ page }) => {
    await installRoutes(page, false);
    await page.goto('/demo');

    await expect(page.getByTestId('demo-capabilities-unavailable')).toContainText(
      'n’a pas répondu'
    );
    await expect(page.getByTestId('demo-capabilities')).toHaveCount(0);
    await expect(page.getByRole('link', { name: 'Ouvrir le démonstrateur' })).toBeVisible();
  });
});
