/**
 * The SMS page's grounds alternate, as the browser paints them (charter « Grounds
 * alternate », owner remark 2026-11-08): a fold on the page is the card, what it holds
 * stands on the page's background, a fold within it holds the card again — in light and
 * in dark, on a phone and on a desktop.
 */
import { test, expect, idleNotificationStream } from '../fixtures';
import { appConfig } from '../fixtures/dashboard-shell';

const id = 'df63b582-413f-4fd4-9f63-df30d1d3a4a2';
const sms = {
  id,
  sender: '+33612345678',
  display_name: 'Camille',
  identity_source: 'contact',
  identity_state: 'resolved',
  relation_key: null,
  body: 'Dîner demain à 20 h ?',
  received_at: '2026-10-19T12:00:00Z',
  date_kind: 'received',
  origin: 'iphone',
};
const page1 = { total: 1, revision: 1, as_of: '2026-10-19T13:00:00Z', next_cursor: null };

for (const scheme of ['light', 'dark'] as const) {
  for (const width of [390, 1280]) {
    test(`SMS grounds alternate in ${scheme} at ${width}px`, async ({
      page,
      authenticate,
      mockApi,
    }, testInfo) => {
      // The theme is the app's own choice (next-themes, `theme` in local storage).
      await page.addInitScript(theme => localStorage.setItem('theme', theme), scheme);
      await page.setViewportSize({ width, height: 900 });
      await authenticate({ language: 'fr', timezone: 'Europe/Paris' });
      await mockApi([
        idleNotificationStream,
        {
          url: '**/api/v1/config',
          json: { ...appConfig, features: { ...appConfig.features, sms_enabled: true } },
        },
        { url: '**/api/v1/sms/search', json: { items: [sms], ...page1 } },
        {
          url: '**/api/v1/sms/senders**',
          json: {
            items: [{ ...sms, total: 1, latest_at: sms.received_at }],
            ...page1,
          },
        },
        {
          url: '**/api/v1/sms/blocked-senders**',
          json: {
            blocks: [{ id: 'b1', sender: '+33 6 00 00 00 00' }],
            total: 1,
            as_of: sms.received_at,
            next_cursor: null,
          },
        },
        { url: `**/api/v1/sms/${id}`, json: sms },
      ]);
      await page.goto(`/fr/dashboard/sms?message=${id}`);
      const main = page.locator('main');
      const archive = main.locator('details').filter({
        has: page.locator('summary', { hasText: 'Consulter mes SMS' }),
      });
      const focused = main.locator('div[tabindex="-1"][aria-label="Mes SMS"]');
      await expect(focused).toContainText(sms.body);
      const sender = archive.locator('details').filter({
        has: page.locator('summary', { hasText: sms.display_name }),
      });
      await sender.locator('summary').click();
      const senderDay = sender.locator('div.rounded-xl').filter({ hasText: sms.body });
      await expect(senderDay).toBeVisible();
      const blocked = main.locator('details').filter({
        has: page.locator('summary', { hasText: 'Expéditeurs bloqués' }),
      });
      await blocked.locator('summary').click();
      const record = blocked.locator('li').filter({ hasText: '+33 6 00 00 00 00' });
      await expect(record).toBeVisible();

      const ground = (locator: typeof main) =>
        locator.evaluate(element => getComputedStyle(element).backgroundColor);
      // The two grounds as this theme resolves them, read on probes.
      const tokens = await page.evaluate(() => {
        const probe = (className: string) => {
          const element = document.createElement('div');
          element.className = className;
          document.body.appendChild(element);
          const color = getComputedStyle(element).backgroundColor;
          element.remove();
          return color;
        };
        return { background: probe('bg-background'), card: probe('bg-card') };
      });
      expect(tokens.card).not.toBe(tokens.background);
      expect(await ground(archive)).toBe(tokens.card);
      // What the archive holds stands on the page's background…
      expect(await ground(focused)).toBe(tokens.background);
      expect(await ground(sender)).toBe(tokens.background);
      expect(await ground(record)).toBe(tokens.background);
      // …and the fold within it holds the card again.
      expect(await ground(senderDay)).toBe(tokens.card);

      await page.screenshot({
        path: testInfo.outputPath(`sms-grounds-${scheme}-${width}.png`),
        fullPage: true,
      });
    });
  }
}
