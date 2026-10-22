/** SMS home: real rendering, account timezone and archive navigation. */
import { test, expect, idleNotificationStream } from '../fixtures';
import { appConfig } from '../fixtures/dashboard-shell';
import { homeRoutes, homeBriefing, HOME_ORDER } from '../fixtures/dashboard-home';
import { awaitStyledPage, expectNoOverflow } from './overflow-report';
import { scanPage } from '../a11y/scan';
test.use({ timezoneId: 'Pacific/Honolulu' });
for (const width of [390, 1280]) {
  test(`SMS home latest messages and archive @ ${width}px`, async ({
    page,
    authenticate,
    mockApi,
  }, testInfo) => {
    await page.setViewportSize({ width, height: 950 });
    await page.clock.setFixedTime(new Date('2026-10-20T08:00:00Z'));
    const user = await authenticate({ language: 'fr', timezone: 'Europe/Paris' });
    const payload = homeBriefing();
    const messages = Array.from({ length: 10 }, (_, index) => ({
      id: `10000000-0000-4000-8000-${String(index + 1).padStart(12, '0')}`,
      sender: '+33612345678',
      display_name: `Camille ${index + 1}`,
      received_at: `2026-10-${index < 5 ? '20' : '17'}T07:${String(59 - index).padStart(2, '0')}:00Z`,
      date_kind: 'received',
      origin: 'iphone',
      identity_source: 'raw',
      identity_state: 'unresolved',
      relation_key: null,
      body: `SMS ${index + 1} <img src=x onerror=alert(1)> ${'texte privé '.repeat(10)}`,
    }));
    payload.cards.sms = {
      status: 'ok',
      data: {
        timezone: 'Europe/Paris',
        total: 137,
        window_total: 5,
        window_start: '2026-10-19T08:00:00Z',
        as_of: '2026-10-20T08:00:00Z',
        latest_at: messages[0].received_at,
        items: messages.map(message => ({
          id: message.id,
          sender: message.sender,
          display_name: message.display_name,
          received_at: message.received_at,
          date_kind: message.date_kind,
          body_excerpt: message.body,
          body_truncated: false,
        })),
      },
      generated_at: '2026-10-20T08:00:00Z',
      error_code: null,
      error_message: null,
      from_cache: false,
      stale_generated_at: null,
      last_attempt_at: null,
    };
    const paid: string[] = [];
    page.on('request', request => {
      if (request.url().endsWith('/briefing/synthesis')) paid.push(request.url());
    });
    await mockApi([
      {
        url: '**/api/v1/sms/senders**',
        json: {
          items: [],
          total: 0,
          as_of: '2026-10-20T08:00:00Z',
          revision: 1,
          next_cursor: null,
        },
      },
      ...homeRoutes(user, payload),
      idleNotificationStream,
      {
        url: '**/api/v1/config',
        json: { ...appConfig, features: { ...appConfig.features, sms_enabled: true } },
      },
      {
        url: '**/api/v1/briefing/preferences',
        json: { order: ['sms', ...HOME_ORDER], hidden: [] },
      },
      {
        url: '**/api/v1/sms/search',
        method: 'POST',
        json: {
          items: messages,
          total: 137,
          as_of: '2026-10-20T08:00:00Z',
          revision: 1,
          next_cursor: 'opaque-next-page',
        },
      },
      { url: `**/api/v1/sms/${messages[0].id}`, json: messages[0] },
      {
        url: '**/api/v1/sms/settings',
        json: {
          preferences: { ingestion_enabled: true, assistant_enabled: false, push_enabled: true },
          usage: {
            message_count: 137,
            receipt_count: 137,
            logical_bytes: 1024,
            max_logical_bytes: 2048,
            max_receipts: 1000,
            last_received_at: messages[0].received_at,
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
      },
      {
        url: '**/api/v1/sms/tokens**',
        json: { tokens: [], total: 0, as_of: messages[0].received_at, next_cursor: null },
      },
      {
        url: '**/api/v1/sms/blocked-senders**',
        json: { blocks: [], total: 0, as_of: messages[0].received_at, next_cursor: null },
      },
    ]);
    await page.goto('/fr/dashboard');
    await awaitStyledPage(page, `sms-home-${width}`);
    const card = page.getByRole('region', { name: 'Mes SMS', exact: true });
    await expect(card).toBeVisible();
    await card.scrollIntoViewIfNeeded();
    await expect(card.getByText('137', { exact: true })).toBeVisible();
    const rows = card.getByRole('listitem');
    await expect(rows).toHaveCount(10);
    await expect(rows.first().getByText(messages[0].body, { exact: true })).toBeVisible();
    await expect(rows.first().getByText(/09:59/)).toBeVisible();
    await expect(card.getByRole('link', { name: 'Ouvrir Mes SMS' })).toHaveCount(0);
    await expect(card.locator('img[src="x"]')).toHaveCount(0);
    await page.screenshot({ path: testInfo.outputPath('sms-home.png') });
    await expectNoOverflow(page, `sms-home-${width}`);
    const { blocking, summary } = await scanPage(page, testInfo, `sms-home-${width}`);
    expect(blocking, summary).toHaveLength(0);
    expect(paid).toHaveLength(1);
    await rows.first().getByRole('button').focus();
    await page.keyboard.press('Enter');
    await expect(page).toHaveURL(
      new RegExp(`/dashboard/settings\\?section=sms&message=${messages[0].id}$`)
    );
    const focused = page.locator('#settings-section-sms div[tabindex="-1"][aria-label="Mes SMS"]');
    await expect(focused.getByText(messages[0].body, { exact: true })).toBeVisible();
  });
}
