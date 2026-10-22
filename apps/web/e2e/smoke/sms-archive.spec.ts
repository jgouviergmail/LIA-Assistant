/** Personal SMS: actual page, literal content, grouping, privacy and mobile reflow. */
import { test, expect, idleNotificationStream, type MockRoute } from '../fixtures';
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
const settingsRoutes: MockRoute[] = [
  {
    url: '**/api/v1/sms/senders**',
    json: {
      items: [],
      total: 0,
      as_of: sms.received_at,
      revision: 1,
      next_cursor: null,
    },
  },
  {
    url: '**/api/v1/sms/settings',
    json: {
      preferences: { ingestion_enabled: true, assistant_enabled: false, push_enabled: true },
      usage: {
        message_count: 1,
        receipt_count: 1,
        logical_bytes: 1024,
        max_logical_bytes: 2048,
        max_receipts: 100,
        last_received_at: sms.received_at,
      },
      device_deliveries: { pending: 0, sending: 0, sent: 0, failed: 0, unknown: 0, cancelled: 0 },
    },
  },
  {
    url: '**/api/v1/sms/tokens**',
    json: { tokens: [], total: 0, as_of: sms.received_at, next_cursor: null },
  },
  {
    url: '**/api/v1/sms/blocked-senders**',
    json: { blocks: [], total: 0, as_of: sms.received_at, next_cursor: null },
  },
];
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
    let failNextSearch = false;
    await mockApi([
      idleNotificationStream,
      ...settingsRoutes,
      {
        url: '**/api/v1/config',
        json: { ...appConfig, features: { ...appConfig.features, sms_enabled: true } },
      },
      {
        url: '**/api/v1/sms/search',
        handler: async route => {
          searches.push({ url: route.request().url(), body: route.request().postDataJSON() });
          if (failNextSearch) {
            failNextSearch = false;
            await route.fulfill({ status: 503, json: { detail: 'Synthetic read failure' } });
            return;
          }
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
    await expect(page).toHaveURL(/\/(?:fr\/)?dashboard\/settings\?section=sms$/);
    // In settings the archive sits in its own disclosure and draws no heading
    // of its own: the region keeps its name.
    await expect(page.getByRole('region', { name: 'Mes SMS', exact: true })).toBeVisible({
      timeout: 15000,
    });
    await expect(page.getByRole('button', { name: 'Par expéditeur', exact: true })).toHaveAttribute(
      'aria-pressed',
      'true'
    );
    await page.getByRole('button', { name: 'Par jour', exact: true }).click();
    await expect(page.getByText(sms.body, { exact: true })).toBeVisible();
    const section = page.locator('#settings-section-sms');
    const archiveHeading = section.locator('summary').filter({ hasText: 'Consulter mes SMS' });
    await expect(archiveHeading.locator('..')).toHaveAttribute('open');
    const summaries = await section.locator('details > summary').allTextContents();
    expect(summaries.findIndex(text => text.includes('Consulter mes SMS'))).toBe(
      summaries.findIndex(text => text.includes('Statistiques')) + 1
    );
    await archiveHeading.focus();
    await page.keyboard.press('Space');
    await expect(page.getByText(sms.body, { exact: true })).toHaveCount(0);
    await expect(archiveHeading).toBeFocused();
    await page.keyboard.press('Enter');
    await page.getByRole('button', { name: 'Par jour', exact: true }).click();
    await expect(page.getByText(sms.body, { exact: true })).toBeVisible();
    await expect(page.locator('img[src="x"]')).toHaveCount(0);
    const search = page.getByRole('searchbox');
    await search.fill('dîner privé');
    failNextSearch = true;
    await search.press('Enter');
    const archive = section.getByRole('region', { name: 'Mes SMS', exact: true });
    await expect(archive.getByRole('alert')).toBeVisible();
    await expect(search).toHaveValue('dîner privé');
    await archive.getByRole('button', { name: 'Actualiser', exact: true }).click();
    await expect
      .poll(() => searches.some(entry => JSON.stringify(entry.body).includes('dîner privé')))
      .toBe(true);
    expect(searches.every(entry => !entry.url.includes('priv'))).toBe(true);
    await expect(page.getByText(sms.body, { exact: true })).toBeVisible();
    await expect(archive.getByRole('alert')).toHaveCount(0);
    await expect(search).toHaveValue('dîner privé');
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

test('an existing notification link focuses its message inside SMS settings', async ({
  page,
  authenticate,
  mockApi,
}) => {
  let erased = false;
  await authenticate({ language: 'fr' });
  await mockApi([
    idleNotificationStream,
    ...settingsRoutes,
    {
      url: '**/api/v1/config',
      json: { ...appConfig, features: { ...appConfig.features, sms_enabled: true } },
    },
    {
      url: '**/api/v1/sms/search',
      method: 'POST',
      json: { items: [], total: 0, revision: 1, as_of: sms.received_at, next_cursor: null },
    },
    {
      url: `**/api/v1/sms/${id}`,
      handler: route =>
        route.fulfill(erased ? { status: 404, json: { detail: 'not found' } } : { json: sms }),
    },
    {
      url: '**/api/v1/sms/commands',
      method: 'POST',
      json: {
        command_id: id,
        operation_id: 'sms_messages.delete',
        content_digest: 'a'.repeat(64),
        before: {
          sms_messages_to_delete: {
            count: 1,
            from_ts: null,
            to_ts: null,
            all_messages: true,
            sender_id: null,
            message_ids: [],
          },
        },
        after: { deleted_sms_messages: 1 },
        expires_at: new Date(Date.now() + 3600000).toISOString(),
      },
    },
    {
      url: `**/api/v1/sms/commands/${id}/confirm`,
      method: 'POST',
      handler: async route => {
        erased = true;
        await route.fulfill({
          json: { outcome: { success: true, committed: true, phase: 'committed' } },
        });
      },
    },
  ]);
  await page.goto(`/fr/dashboard/sms?message=${id}`);
  await expect(page).toHaveURL(
    new RegExp(`/(?:fr/)?dashboard/settings\\?section=sms&message=${id}$`)
  );
  const focused = page.locator('#settings-section-sms div[tabindex="-1"][aria-label="Mes SMS"]');
  await expect(focused.getByText(sms.body, { exact: true })).toBeVisible();
  await expect(focused).toBeFocused();
  const section = page.locator('#settings-section-sms');
  await section.locator('summary').filter({ hasText: 'Suppression des SMS' }).click();
  const erase = section.getByRole('button', { name: 'Supprimer tous mes SMS', exact: true });
  await erase.click();
  await page
    .getByRole('alertdialog')
    .getByRole('button', { name: 'Confirmer ce changement', exact: true })
    .click();
  await expect(focused).toHaveCount(0);
  await expect(section.getByText(sms.body, { exact: true })).toHaveCount(0);
  await expect(erase).toBeFocused();
});

for (const width of [390, 1280]) {
  for (const scope of ['message', 'sender', 'day'] as const) {
    test(`review and delete SMS by ${scope} @ ${width}px`, async ({
      page,
      authenticate,
      mockApi,
    }) => {
      await page.setViewportSize({ width, height: 950 });
      await authenticate({ language: 'fr', timezone: 'Europe/Paris' });
      let erased = false;
      let confirmed = 0;
      const selected =
        scope === 'message'
          ? { message_ids: [id] }
          : scope === 'sender'
            ? { sender_id: id }
            : { from_ts: '2026-10-18T22:00:00.000Z', to_ts: '2026-10-19T22:00:00.000Z' };
      await mockApi([
        idleNotificationStream,
        ...settingsRoutes,
        {
          url: '**/api/v1/config',
          json: { ...appConfig, features: { ...appConfig.features, sms_enabled: true } },
        },
        {
          url: '**/api/v1/sms/senders**',
          handler: route =>
            route.fulfill({
              json: {
                items: erased ? [] : [{ ...sms, total: 1, latest_at: sms.received_at }],
                total: erased ? 0 : 1,
                revision: 1,
                as_of: sms.received_at,
                next_cursor: null,
              },
            }),
        },
        {
          url: '**/api/v1/sms/search',
          method: 'POST',
          handler: route =>
            route.fulfill({
              json: {
                items: erased ? [] : [sms],
                total: erased ? 0 : 1,
                revision: 1,
                as_of: sms.received_at,
                next_cursor: null,
              },
            }),
        },
        {
          url: '**/api/v1/sms/commands',
          method: 'POST',
          handler: route => {
            const body: unknown = route.request().postDataJSON();
            expect(body).toEqual({ operation_id: 'sms_messages.delete', payload: selected });
            return route.fulfill({
              json: {
                command_id: id,
                operation_id: 'sms_messages.delete',
                content_digest: 'a'.repeat(64),
                before: {
                  sms_messages_to_delete: {
                    count: 1,
                    all_messages: false,
                    sender_id: null,
                    from_ts: null,
                    to_ts: null,
                    message_ids: [],
                    ...selected,
                  },
                },
                after: { deleted_sms_messages: 1 },
                expires_at: '2099-01-01T00:00:00Z',
              },
            });
          },
        },
        { url: `**/api/v1/sms/commands/${id}/cancel`, method: 'POST', json: { cancelled: true } },
        {
          url: `**/api/v1/sms/commands/${id}/confirm`,
          method: 'POST',
          handler: route => {
            confirmed += 1;
            erased = true;
            return route.fulfill({
              json: {
                outcome: { success: true, committed: true, phase: 'committed' },
                secret: null,
              },
            });
          },
        },
      ]);
      await page.goto('/fr/dashboard/settings?section=sms');
      const section = page.locator('#settings-section-sms');
      if (scope === 'day')
        await section.getByRole('button', { name: 'Par jour', exact: true }).click();
      else await section.locator('summary').filter({ hasText: 'Camille' }).click();
      await expect(section.getByText(sms.body, { exact: true })).toBeVisible();
      const labels = {
        message: 'Supprimer ce SMS',
        sender: 'Supprimer les SMS de cet expéditeur',
        day: 'Supprimer les SMS de ce jour',
      };
      const erase = section.getByRole('button', { name: new RegExp(`^${labels[scope]} ·`) });
      if (scope === 'message') {
        const stamp = await section.locator('article time').boundingBox();
        const icon = await erase.boundingBox();
        expect(stamp).not.toBeNull();
        expect(icon).not.toBeNull();
        expect(icon!.y).toBeGreaterThanOrEqual(stamp!.y + stamp!.height);
        await expect(erase).toHaveText('');
      }
      await erase.focus();
      await page.keyboard.press('Enter');
      const dialog = page.getByRole('alertdialog');
      if (scope === 'message') {
        await expect.poll(() => confirmed).toBe(1);
      } else {
        await expect(dialog).toBeVisible();
        expect(confirmed).toBe(0);
        await dialog.getByRole('button', { name: 'Annuler', exact: true }).click();
        await expect(erase).toBeFocused();
        expect(confirmed).toBe(0);
        await page.keyboard.press('Enter');
        const confirm = dialog.getByRole('button', {
          name: 'Confirmer ce changement',
          exact: true,
        });
        await confirm.focus();
        await page.keyboard.press('Enter');
      }
      await expect(dialog).toHaveCount(0);
      await expect(section.getByText(sms.body, { exact: true })).toHaveCount(0);
      await expect(
        section.locator('summary').filter({ hasText: 'Consulter mes SMS' })
      ).toBeFocused();
      expect(confirmed).toBe(1);
      await expect(
        section.getByText('Date fournie par Raccourcis ; réception exacte non confirmée.')
      ).toHaveCount(0);
    });
  }
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
  await section.locator('summary').filter({ hasText: 'API d’ingestion' }).click();
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
