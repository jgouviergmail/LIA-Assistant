/** SMS uses the same lazy chronological history and bottom pagination as the hub. */
import { test, expect, idleNotificationStream } from '../fixtures';
import { appConfig } from '../fixtures/dashboard-shell';
import { scanPage } from '../a11y/scan';
import { awaitStyledPage, expectNoOverflow } from './overflow-report';

const messages = Array.from({ length: 12 }, (_, index) => ({
  id: `10000000-0000-4000-8000-${String(index + 1).padStart(12, '0')}`,
  sender: index % 2 ? 'Camille' : 'Alice',
  display_name: index % 2 ? 'Camille' : 'Alice',
  body:
    index === 0 ? '<script>texte reçu</script> ' + 'motlong'.repeat(80) : `SMS reçu ${index + 1}`,
  received_at: new Date(Date.UTC(2026, 9, 20, 12 - index)).toISOString(),
  date_kind: 'received',
  origin: 'iphone',
  identity_source: 'raw',
  identity_state: 'unresolved',
  relation_key: null,
}));

for (const width of [390, 1280]) {
  test(`SMS alerts chronology and pagination at ${width}px`, async ({
    page,
    authenticate,
    mockApi,
  }, info) => {
    await page.setViewportSize({ width, height: 900 });
    await authenticate({ language: 'fr', timezone: 'Europe/Paris' });
    const reads: unknown[] = [];
    await mockApi([
      idleNotificationStream,
      {
        url: '**/api/v1/config',
        json: { ...appConfig, features: { ...appConfig.features, sms_enabled: true } },
      },
      {
        url: '**/api/v1/notifications/hub-counts',
        json: {
          reminders: 0,
          scheduled: 0,
          peer_messages: 0,
          proactive: 0,
          interests: 0,
          offers: 0,
          workboard: 0,
          sms: 12,
        },
      },
      {
        url: '**/api/v1/sms/search',
        method: 'POST',
        handler: async route => {
          const query = route.request().postDataJSON();
          reads.push(query);
          await route.fulfill({
            json: {
              items: query.cursor ? messages.slice(10) : messages.slice(0, 10),
              total: 12,
              revision: 1,
              as_of: messages[0].received_at,
              next_cursor: query.cursor ? null : 'opaque-second-page',
            },
          });
        },
      },
    ]);
    await page.goto('/fr/dashboard/notifications');
    await awaitStyledPage(page, 'SMS alerts');
    const disclosure = page
      .locator('details')
      .filter({ has: page.locator('summary').getByText('Mes SMS', { exact: true }) });
    const toggle = disclosure.locator(':scope > summary');
    await expect(toggle).toContainText('12');
    expect(reads).toEqual([]);
    await toggle.click();
    await expect(disclosure.getByRole('listitem')).toHaveCount(10);
    expect(
      await disclosure
        .locator('time')
        .evaluateAll(elements => elements.map(element => element.getAttribute('datetime')))
    ).toEqual(messages.slice(0, 10).map(item => item.received_at));
    // An SMS names its sender where its words begin (owner request
    // 2026-10-21): the sender's marker opens the message's own paragraph.
    const first = disclosure.getByRole('listitem').first().getByRole('paragraph');
    await expect(first).toContainText(messages[0].body);
    await expect(first.locator(':scope > :first-child')).toHaveText(messages[0].display_name);
    await expect(disclosure.getByRole('search')).toHaveCount(0);
    await expect(disclosure.getByRole('button', { name: 'Par expéditeur' })).toHaveCount(0);
    const next = disclosure.getByRole('button', { name: 'Suivant', exact: true });
    await next.focus();
    await page.keyboard.press('Enter');
    await expect(disclosure.getByRole('listitem')).toHaveCount(2);
    await expect(next).toBeFocused();
    await expect(disclosure.getByText('SMS reçu 11')).toBeVisible();
    expect(reads).toEqual([{ limit: 10 }, { limit: 10, cursor: 'opaque-second-page' }]);
    await disclosure.getByRole('button', { name: 'Précédent', exact: true }).click();
    await expect(disclosure.getByRole('listitem')).toHaveCount(10);
    await expectNoOverflow(page, 'SMS alerts');
    const audit = await scanPage(page, info, `sms-alerts-${width}`);
    expect(audit.blocking, audit.summary).toEqual([]);
    await page.screenshot({ path: info.outputPath(`sms-alerts-${width}.png`), fullPage: true });
  });
}
