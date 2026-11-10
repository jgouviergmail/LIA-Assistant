/**
 * The blocked-sender field keeps room to type a name or a number (owner request 2026-11-08):
 * on a phone the long « block » button goes under the field instead of squeezing it; on a
 * desktop both share one line.
 */
import { test, expect, idleNotificationStream } from '../fixtures';
import { appConfig } from '../fixtures/dashboard-shell';

const empty = { total: 0, revision: 1, as_of: '2026-10-19T13:00:00Z', next_cursor: null };

for (const width of [390, 1280]) {
  test(`the blocked-sender field keeps its room at ${width}px`, async ({
    page,
    authenticate,
    mockApi,
  }) => {
    await page.setViewportSize({ width, height: 900 });
    await authenticate({ language: 'fr', timezone: 'Europe/Paris' });
    await mockApi([
      idleNotificationStream,
      {
        url: '**/api/v1/config',
        json: { ...appConfig, features: { ...appConfig.features, sms_enabled: true } },
      },
      { url: '**/api/v1/sms/search', json: { items: [], ...empty } },
      { url: '**/api/v1/sms/senders**', json: { items: [], ...empty } },
      {
        url: '**/api/v1/sms/blocked-senders**',
        json: { blocks: [], total: 0, as_of: empty.as_of, next_cursor: null },
      },
    ]);
    await page.goto('/fr/dashboard/sms');
    const blocked = page.locator('main details').filter({
      has: page.locator('summary', { hasText: 'Expéditeurs bloqués' }),
    });
    await blocked.locator('summary').click();
    const field = blocked.getByLabel('Nom ou numéro exact de l’expéditeur');
    const button = blocked.getByRole('button', { name: 'Bloquer les prochains SMS' });
    await expect(button).toBeVisible();
    const form = blocked.locator('form');
    const [fieldBox, buttonBox, formBox] = await Promise.all([
      field.boundingBox(),
      button.boundingBox(),
      form.boundingBox(),
    ]);
    if (!fieldBox || !buttonBox || !formBox) throw new Error('unmeasured form');
    // The button never leaves the form.
    expect(buttonBox.x + buttonBox.width).toBeLessThanOrEqual(formBox.x + formBox.width + 1);
    if (width < 640) {
      // A phone: the field takes the line, the button goes under it.
      expect(fieldBox.width).toBeGreaterThanOrEqual(formBox.width * 0.9);
      expect(buttonBox.y).toBeGreaterThanOrEqual(fieldBox.y + fieldBox.height);
    } else {
      // A desktop: one line, the field the wider of the two.
      expect(Math.abs(buttonBox.y - fieldBox.y)).toBeLessThan(fieldBox.height);
      expect(fieldBox.width).toBeGreaterThan(buttonBox.width);
    }
  });
}
