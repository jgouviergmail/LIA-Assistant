/** Personal SMS: actual page, literal content, grouping, privacy and mobile reflow. */
import { test, expect, idleNotificationStream } from '../fixtures';
import { appConfig } from '../fixtures/dashboard-shell';
import { scanPage } from '../a11y/scan';
const id = 'df63b582-413f-4fd4-9f63-df30d1d3a4a2';
const sms = {
  id,
  sender: '+33612345678',
  display_name: 'Camille',
  identity_source: 'contact',
  identity_state: 'resolved',
  relation_key: null,
  body: '<img src=x onerror=alert(1)> Dîner demain ? ' + 'longtexte'.repeat(60),
  received_at: '2026-10-19T12:00:00Z',
  date_kind: 'received',
  origin: 'iphone',
};
for (const width of [390, 1280]) {
  test(`SMS archive is usable and safe at ${width}px`, async ({
    page,
    authenticate,
    mockApi,
  }, testInfo) => {
    const browserErrors: string[] = [];
    page.on('pageerror', error => browserErrors.push(error.message));
    await page.setViewportSize({ width, height: 900 });
    await authenticate({ language: 'fr', timezone: 'Europe/Paris' });
    const searches: { url: string; body: unknown }[] = [];
    await mockApi([
      idleNotificationStream,
      {
        url: '**/api/v1/config',
        json: { ...appConfig, features: { ...appConfig.features, sms_enabled: true } },
      },
      {
        url: '**/api/v1/sms/search',
        handler: async route => {
          searches.push({ url: route.request().url(), body: route.request().postDataJSON() });
          await route.fulfill({
            json: {
              items: [sms],
              total: 1,
              revision: 1,
              as_of: '2026-10-19T13:00:00Z',
              next_cursor: null,
            },
          });
        },
      },
      {
        url: '**/api/v1/sms/senders**',
        json: {
          items: [
            {
              id,
              sender: sms.sender,
              display_name: sms.display_name,
              identity_source: 'contact',
              identity_state: 'resolved',
              relation_key: null,
              total: 1,
              latest_at: sms.received_at,
            },
          ],
          total: 1,
          revision: 1,
          as_of: '2026-10-19T13:00:00Z',
          next_cursor: null,
        },
      },
    ]);
    await page.goto('/fr/dashboard/sms');
    await expect(page.getByRole('heading', { name: 'Mes SMS', exact: true })).toBeVisible({
      timeout: 15000,
    });
    await expect(page.getByText(sms.body, { exact: true })).toBeVisible();
    await expect(page.locator('img[src="x"]')).toHaveCount(0);
    const search = page.getByRole('searchbox');
    await search.fill('dîner privé');
    await search.press('Enter');
    await expect
      .poll(() => searches.some(entry => JSON.stringify(entry.body).includes('dîner privé')))
      .toBe(true);
    expect(searches.every(entry => !entry.url.includes('priv'))).toBe(true);
    await expect(page.getByText(sms.body, { exact: true })).toBeVisible();
    const { blocking, summary } = await scanPage(page, testInfo, `sms-${width}`);
    expect(blocking, summary).toHaveLength(0);
    expect(
      await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)
    ).toBe(true);
    await search.focus();
    await page.keyboard.press('Tab');
    await expect(page.getByRole('button', { name: 'Rechercher', exact: true })).toBeFocused();
    expect(browserErrors).toEqual([]);
    await page.screenshot({ path: testInfo.outputPath(`sms-${width}.png`), fullPage: true });
  });
}

test('a token requires explicit browser approval and is cleared without persistence', async ({
  page,
  authenticate,
  mockApi,
}, testInfo) => {
  await page.setViewportSize({ width: 390, height: 900 });
  await authenticate({ language: 'fr' });
  let confirmations = 0;
  const fakeSecret = 'pi_synthetic_browser_secret_only';
  const stamp = '2026-10-19T12:00:00Z';
  await mockApi([
    idleNotificationStream,
    {
      url: '**/api/v1/config',
      json: { ...appConfig, features: { ...appConfig.features, sms_enabled: true } },
    },
    {
      url: '**/api/v1/sms/settings',
      json: {
        preferences: { ingestion_enabled: true, assistant_enabled: false, push_enabled: true },
        usage: {
          message_count: 0,
          receipt_count: 0,
          logical_bytes: 0,
          max_logical_bytes: 1073741824,
          max_receipts: 1000000,
          last_received_at: null,
        },
        device_deliveries: { pending: 0, sending: 0, sent: 0, failed: 0, unknown: 0, cancelled: 0 },
      },
    },
    {
      url: '**/api/v1/sms/tokens**',
      json: { tokens: [], total: 0, as_of: stamp, next_cursor: null },
    },
    {
      url: '**/api/v1/sms/blocked-senders**',
      json: { blocks: [], total: 0, as_of: stamp, next_cursor: null },
    },
    {
      url: '**/api/v1/sms/commands',
      method: 'POST',
      json: {
        command_id: id,
        operation_id: 'sms_token.create',
        content_digest: 'a'.repeat(64),
        before: { ingestion_token_to_create: null },
        after: { ingestion_token_to_create: { label: 'iPhone', source_id: null } },
        expires_at: new Date(Date.now() + 3600000).toISOString(),
      },
    },
    {
      url: `**/api/v1/sms/commands/${id}/confirm`,
      method: 'POST',
      handler: async route => {
        confirmations++;
        await route.fulfill({
          json: {
            outcome: { success: true, committed: true, phase: 'committed' },
            secret: { token: fakeSecret },
          },
        });
      },
    },
  ]);
  await page.goto('/fr/dashboard/settings?section=sms');
  const section = page.locator('#settings-section-sms');
  await expect(section.getByRole('button', { name: 'Créer un jeton', exact: true })).toBeVisible({
    timeout: 30000,
  });
  await section.getByRole('button', { name: 'Créer un jeton', exact: true }).click();
  const dialog = page.getByRole('alertdialog');
  await expect(dialog).toBeVisible();
  expect(confirmations).toBe(0);
  await expect(dialog.getByText('iPhone', { exact: true })).toBeVisible();
  const { blocking, summary } = await scanPage(page, testInfo, 'sms-confirmation-mobile');
  expect(blocking, summary).toHaveLength(0);
  await dialog.getByRole('button', { name: 'Confirmer ce changement', exact: true }).click();
  const secret = section.locator('input[type="password"]');
  await expect(secret).toHaveValue(fakeSecret);
  expect(confirmations).toBe(1);
  expect(await page.evaluate(() => JSON.stringify([localStorage, sessionStorage]))).not.toContain(
    fakeSecret
  );
  await section.getByRole('button', { name: 'Fermer', exact: true }).click();
  await expect(section.locator('input[type="password"]')).toHaveCount(0);
});
