/** The SMS source switches and the phone title, in the actual settings layout. */
import { test, expect, idleNotificationStream } from '../fixtures';
import { appConfig } from '../fixtures/dashboard-shell';
import {
  radioOptions,
  radioPreferences,
  radioSources,
} from '../../src/lib/radio/__tests__/fixtures';
import { awaitStyledPage, expectNoOverflow } from './overflow-report';

for (const width of [390, 1280]) {
  test(`SMS phone source and inset panel title @ ${width}px`, async ({
    page,
    authenticate,
    mockApi,
  }) => {
    await page.setViewportSize({ width, height: 950 });
    await authenticate({ language: 'fr' });
    const identity = {
      phone_number: '+33612345678',
      verified: true,
      verified_at: '2026-10-20T08:00:00Z',
      rich_context_enabled: true,
      disabled_domains: [],
      available_domains: ['email', 'sms'],
      verification_pending: false,
      call_mode: 'delegated',
      call_mode_effective: 'delegated',
      live_available: true,
      live_unavailable_reason: null,
    };
    await mockApi([
      idleNotificationStream,
      {
        url: '**/api/v1/config',
        json: { ...appConfig, features: { ...appConfig.features, telephony_enabled: true } },
      },
      { url: '**/api/v1/telephony/identity', method: 'GET', json: identity },
      {
        url: '**/api/v1/telephony/identity',
        method: 'PATCH',
        handler: route => {
          const body: unknown = route.request().postDataJSON();
          expect(body).toEqual({ disabled_domains: ['sms'] });
          return route.fulfill({ json: { ...identity, disabled_domains: ['sms'] } });
        },
      },
    ]);
    await page.goto('/fr/dashboard/settings?section=telephony-identity');
    await awaitStyledPage(page, 'Phone SMS settings');
    const title = 'Ce que LIA peut consulter pour toi en direct';
    const panel = page.getByRole('group', { name: title });
    const heading = panel.getByRole('heading', { name: title });
    await expect(heading).toBeVisible();
    const panelBox = await panel.boundingBox();
    const titleBox = await heading.boundingBox();
    if (!panelBox || !titleBox) throw new Error('Phone panel has no visible geometry');
    expect(titleBox.y).toBeGreaterThan(panelBox.y + 5);
    const sms = panel.getByRole('switch', { name: 'SMS', exact: true });
    await expect(sms).toBeChecked();
    await sms.click();
    await expect(sms).not.toBeChecked();
    await expectNoOverflow(page, 'Phone SMS source');
  });

  test(`SMS Radio source saves its own switch @ ${width}px`, async ({
    page,
    authenticate,
    mockApi,
  }) => {
    await page.setViewportSize({ width, height: 950 });
    await authenticate({ language: 'fr' });
    await mockApi([
      idleNotificationStream,
      {
        url: '**/api/v1/config',
        json: { ...appConfig, features: { ...appConfig.features, radio_enabled: true } },
      },
      { url: '**/api/v1/radio/options', json: radioOptions({ sources: ['sms'] }) },
      { url: '**/api/v1/radio/preferences', method: 'GET', json: radioPreferences() },
      { url: '**/api/v1/radio/sources', json: radioSources() },
      {
        url: '**/api/v1/radio/budget',
        json: { limit_eur: 0, spent_eur: 0, window_hours: 24, lifts_at: null },
      },
      {
        url: '**/api/v1/radio/preferences',
        method: 'PUT',
        handler: route => {
          const body: unknown = route.request().postDataJSON();
          expect(body).toEqual(radioPreferences({ disabled_sources: ['sms'] }));
          return route.fulfill({ json: radioPreferences({ disabled_sources: ['sms'] }) });
        },
      },
    ]);
    await page.goto('/fr/dashboard/settings?section=radio');
    await awaitStyledPage(page, 'Radio SMS settings');
    await page.locator('summary').filter({ hasText: 'Ta vie à l’antenne' }).click();
    const sms = page
      .locator('#settings-section-radio')
      .getByRole('switch', { name: 'SMS', exact: true });
    await expect(sms).toBeChecked();
    await sms.click();
    await expect(sms).not.toBeChecked();
    await expectNoOverflow(page, 'Radio SMS source');
  });
}
