/** Real settings shell: folded setup, direct toggles, failure/retry and preserved focus. */
import { test, expect, idleNotificationStream } from '../fixtures';
import { appConfig } from '../fixtures/dashboard-shell';
import { scanPage } from '../a11y/scan';
import { expectNoOverflow } from './overflow-report';

for (const width of [390, 1280]) {
  test(`SMS settings folds and direct saves @ ${width}px`, async ({
    page,
    authenticate,
    mockApi,
  }, testInfo) => {
    await page.setViewportSize({ width, height: 950 });
    await authenticate({ language: 'fr' });
    let preferences = { ingestion_enabled: true, assistant_enabled: false, push_enabled: true };
    let failPush = true;
    const writes: unknown[] = [];
    const commands: string[] = [];
    const errors: string[] = [];
    page.on('pageerror', error => errors.push(error.message));
    page.on('request', request => {
      if (request.url().includes('/sms/commands')) commands.push(request.url());
    });
    const stamp = '2026-10-20T08:00:00Z';
    await mockApi([
      {
        url: '**/api/v1/sms/senders**',
        json: { items: [], total: 0, as_of: stamp, revision: 1, next_cursor: null },
      },
      idleNotificationStream,
      {
        url: '**/api/v1/config',
        json: { ...appConfig, features: { ...appConfig.features, sms_enabled: true } },
      },
      {
        url: '**/api/v1/sms/settings',
        handler: route =>
          route.fulfill({
            json: {
              preferences,
              usage: {
                message_count: 2,
                receipt_count: 2,
                logical_bytes: 1024,
                max_logical_bytes: 2048,
                max_receipts: 100,
                last_received_at: stamp,
              },
              device_deliveries: {
                pending: 0,
                sending: 0,
                sent: 0,
                failed: 0,
                unknown: 0,
                cancelled: 0,
              },
            },
          }),
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
        url: '**/api/v1/sms/search',
        method: 'POST',
        json: { items: [], total: 0, revision: 1, as_of: stamp, next_cursor: null },
      },
      {
        url: '**/api/v1/sms/preferences',
        method: 'PATCH',
        handler: async route => {
          const change: unknown = route.request().postDataJSON();
          writes.push(change);
          if (
            typeof change !== 'object' ||
            change === null ||
            !('field' in change) ||
            !('value' in change) ||
            typeof change.value !== 'boolean'
          )
            throw new Error('Invalid toggle payload');
          if (change.field !== 'assistant_enabled' && change.field !== 'push_enabled')
            throw new Error('Unexpected field');
          if (change.field === 'push_enabled' && failPush) {
            failPush = false;
            await route.fulfill({ status: 503, json: { detail: 'Synthetic save failure' } });
            return;
          }
          preferences = { ...preferences, [change.field]: change.value };
          await route.fulfill({ json: preferences });
        },
      },
    ]);
    await page.goto('/fr/dashboard/settings?section=sms');
    const section = page.locator('#settings-section-sms');
    await expect(section.getByText('2 SMS enregistrés')).toBeVisible();
    const assistantHeading = section.locator('summary').filter({ hasText: 'Accès de l’assistant' });
    for (const title of [
      'API d’ingestion',
      'Accès de l’assistant',
      'Expéditeurs bloqués',
      'Suppression des SMS',
    ]) {
      const heading = section.locator('summary').filter({ hasText: title });
      await expect(heading).toBeVisible();
      await expect(heading.locator('..')).not.toHaveAttribute('open');
    }
    await page.screenshot({
      path: testInfo.outputPath('sms-settings-default.png'),
      fullPage: true,
    });
    await assistantHeading.focus();
    await page.keyboard.press('Enter');
    const assistant = section.getByRole('switch', { name: 'Accès de l’assistant', exact: true });
    await expect(assistant).toBeVisible();
    await assistant.focus();
    await page.keyboard.press('Space');
    await expect(assistant).toBeChecked();
    await expect(assistant).toBeFocused();
    await expect(page.getByRole('alertdialog')).toHaveCount(0);
    const push = section.getByRole('switch', {
      name: 'Push immédiate à chaque nouveau SMS',
      exact: true,
    });
    await expect(push).toHaveAttribute('aria-disabled', 'false');
    await push.focus();
    await page.keyboard.press('Space');
    await expect(section.getByRole('alert')).toBeVisible();
    await expect(push).toBeChecked();
    await expect(push).toBeFocused();
    await expect(push).toHaveAttribute('aria-disabled', 'false');
    await page.keyboard.press('Space');
    await expect(push).not.toBeChecked();
    await expect(section.getByRole('alert')).toHaveCount(0);
    await expect(section.getByText('2 SMS enregistrés')).toBeVisible();
    expect(writes).toEqual([
      { field: 'assistant_enabled', value: true },
      { field: 'push_enabled', value: false },
      { field: 'push_enabled', value: false },
    ]);
    expect(commands).toEqual([]);
    await section.locator('summary').filter({ hasText: 'API d’ingestion' }).click();
    const label = section.getByRole('textbox', { name: 'Nom de la source', exact: true });
    await label.fill('iPhone personnel');
    await section.getByRole('button', { name: 'Actualiser', exact: true }).last().click();
    await expect(label).toHaveValue('iPhone personnel');
    const { blocking, summary } = await scanPage(page, testInfo, `sms-settings-${width}`);
    expect(blocking, summary).toHaveLength(0);
    await expectNoOverflow(page, `sms-settings-${width}`);
    expect(errors).toEqual([]);
    await page.screenshot({ path: testInfo.outputPath('sms-settings.png'), fullPage: true });
  });
}
