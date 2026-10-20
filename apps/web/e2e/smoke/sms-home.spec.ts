/** SMS home: real rendering, account timezone and archive navigation. */
import { test, expect, idleNotificationStream } from '../fixtures';
import { appConfig } from '../fixtures/dashboard-shell';
import { homeRoutes, homeBriefing, HOME_ORDER } from '../fixtures/dashboard-home';
import { awaitStyledPage, expectNoOverflow } from './overflow-report';
import { scanPage } from '../a11y/scan';
test.use({ timezoneId: 'Pacific/Honolulu' });
for (const width of [390, 1280]) {
  test(`SMS home count and archive @ ${width}px`, async ({
    page,
    authenticate,
    mockApi,
  }, testInfo) => {
    await page.setViewportSize({ width, height: 950 });
    await page.clock.setFixedTime(new Date('2026-10-20T08:00:00Z'));
    const user = await authenticate({ language: 'fr', timezone: 'Europe/Paris' });
    const payload = homeBriefing();
    payload.cards.sms = {
      status: 'ok',
      data: {
        timezone: 'Europe/Paris',
        total: 137,
        window_total: 5,
        window_start: '2026-10-19T08:00:00Z',
        as_of: '2026-10-20T08:00:00Z',
        latest_at: '2026-10-20T07:55:00Z',
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
          items: [],
          total: 0,
          as_of: '2026-10-20T08:00:00Z',
          revision: 1,
          next_cursor: null,
        },
      },
    ]);
    await page.goto('/fr/dashboard');
    await awaitStyledPage(page, `sms-home-${width}`);
    const card = page.getByRole('region', { name: 'Mes SMS', exact: true });
    await expect(card).toBeVisible();
    await card.scrollIntoViewIfNeeded();
    await expect(card.getByText('137', { exact: true })).toBeVisible();
    await expect(card.getByText('5', { exact: true })).toBeVisible();
    await expect(card.getByText(/10:00.*10:00/)).toBeVisible();
    await page.screenshot({ path: testInfo.outputPath('sms-home.png') });
    await expectNoOverflow(page, `sms-home-${width}`);
    const { blocking, summary } = await scanPage(page, testInfo, `sms-home-${width}`);
    expect(blocking, summary).toHaveLength(0);
    const link = card.getByRole('link', { name: 'Ouvrir Mes SMS' });
    await expect(link).toHaveAttribute('href', '/fr/dashboard/sms');
    expect(paid).toHaveLength(1);
    await link.click();
    await expect(page).toHaveURL(/\/(?:fr\/)?dashboard\/sms$/);
    await expect(page.getByText('Aucun SMS dans cette sélection.')).toBeVisible();
  });
}
