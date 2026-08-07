/**
 * Guided showroom P0 — axe accessibility gate (telemetry-OFF build).
 *
 * Scans the four key mission states (ready, email decision, open proof
 * drawer, receipt) in dark and light. Critical and serious findings block.
 * Runs only in the dedicated showroom build (`task test:e2e:showroom`).
 */

import { expect, test, type Page } from '@playwright/test';

import { scanPage } from './scan';

async function walkToEmailDecision(page: Page): Promise<void> {
  await page.getByTestId('showroom-pick-overloaded_morning').click();
  await page.getByTestId('showroom-start').click();
  for (let i = 0; i < 6; i += 1) {
    await page.getByTestId('showroom-continue').click();
  }
}

for (const scheme of ['dark', 'light'] as const) {
  test.describe(`showroom axe — ${scheme}`, () => {
    test.use({
      colorScheme: scheme,
      locale: 'fr-FR',
      contextOptions: { reducedMotion: 'reduce' },
    });

    test('mission picker has no blocking violation', async ({ page }, testInfo) => {
      await page.goto('/demo');
      const { blocking, summary } = await scanPage(page, testInfo, `showroom-picker-${scheme}`);
      expect(blocking, summary).toEqual([]);
    });

    test('ready state has no blocking violation', async ({ page }, testInfo) => {
      await page.goto('/demo');
      await page.getByTestId('showroom-pick-overloaded_morning').click();
      const { blocking, summary } = await scanPage(page, testInfo, `showroom-ready-${scheme}`);
      expect(blocking, summary).toEqual([]);
    });

    test('email decision has no blocking violation', async ({ page }, testInfo) => {
      await page.goto('/demo');
      await walkToEmailDecision(page);
      const { blocking, summary } = await scanPage(page, testInfo, `showroom-email-${scheme}`);
      expect(blocking, summary).toEqual([]);
    });

    test('receipt and proof drawer have no blocking violation', async ({ page }, testInfo) => {
      await page.goto('/demo');
      await walkToEmailDecision(page);
      await page
        .getByTestId('showroom-decision-0')
        .getByRole('button', { name: 'Confirmer' })
        .click();
      await page
        .getByTestId('showroom-decision-1')
        .getByRole('button', { name: 'Annuler' })
        .click();
      await expect(page.getByTestId('showroom-receipt')).toBeVisible();
      const receipt = await scanPage(page, testInfo, `showroom-receipt-${scheme}`);
      expect(receipt.blocking, receipt.summary).toEqual([]);

      await page.getByTestId('showroom-proof-open').click();
      await expect(page.getByRole('dialog')).toBeVisible();
      const drawer = await scanPage(page, testInfo, `showroom-drawer-${scheme}`);
      expect(drawer.blocking, drawer.summary).toEqual([]);
    });
  });
}
