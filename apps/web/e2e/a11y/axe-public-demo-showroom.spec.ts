/**
 * Guided showroom P0 — axe accessibility gate (telemetry-OFF build).
 *
 * Scans the key mission states (ready, email decision, open proof drawer,
 * receipt) and the read-only Radio / meeting results in dark and light.
 * Critical and serious findings block.
 * Runs only in the dedicated showroom build (`task test:e2e:showroom`).
 */

import type { Page, TestInfo } from '@playwright/test';

import { expect, test } from '../fixtures';

import { scanPage } from './scan';

async function walkToEmailDecision(page: Page): Promise<void> {
  await page.getByTestId('showroom-pick-overloaded_morning').click();
  await page.getByTestId('showroom-start').click();
  for (let i = 0; i < 6; i += 1) {
    await page.getByTestId('showroom-continue').click();
  }
}

async function walkToReadOnlyReceipt(
  page: Page,
  missionId: 'daily_briefing' | 'config_tour'
): Promise<void> {
  await page.getByTestId(`showroom-pick-${missionId}`).click();
  await page.getByTestId('showroom-start').click();
  const receipt = page.getByTestId('showroom-receipt');
  const decisions = page.locator('[data-testid^="showroom-decision-"]');
  await expect(decisions).toHaveCount(0);
  // Three sources plus planning reach the receipt in five Continue steps.
  // The finite bound makes a stalled / accidental HITL phase fail loudly.
  for (let step = 0; step < 6 && !(await receipt.isVisible()); step += 1) {
    await page.getByTestId('showroom-continue').click();
    await expect(decisions).toHaveCount(0);
  }
  await expect(receipt).toBeVisible();
  await expect(decisions).toHaveCount(0);
}

for (const scheme of ['dark', 'light'] as const) {
  test.describe(`showroom axe — ${scheme}`, () => {
    test.use({
      colorScheme: scheme,
      locale: 'fr-FR',
      contextOptions: { reducedMotion: 'reduce' },
    });

    test.beforeEach(async ({ page, mockApi }) => {
      await mockApi([
        {
          url: '**/api/v1/product/public-demo-link',
          method: 'GET',
          json: { enabled: false, url: null },
        },
      ]);
      // /demo defaults to dark when no stored preference exists. The OS
      // colorScheme alone therefore cannot establish a genuine light scan.
      await page.addInitScript(theme => window.localStorage.setItem('theme', theme), scheme);
    });

    async function scanThemedPage(page: Page, testInfo: TestInfo, label: string) {
      const html = page.locator('html');
      if (scheme === 'dark') {
        await expect(html, `${label} must render the dark theme`).toHaveClass(/\bdark\b/);
      } else {
        await expect(html, `${label} must render the light theme`).not.toHaveClass(/\bdark\b/);
      }
      return scanPage(page, testInfo, label);
    }

    test('mission picker has no blocking violation', async ({ page }, testInfo) => {
      await page.goto('/demo');
      const { blocking, summary } = await scanThemedPage(
        page,
        testInfo,
        `showroom-picker-${scheme}`
      );
      expect(blocking, summary).toEqual([]);
    });

    test('ready state has no blocking violation', async ({ page }, testInfo) => {
      await page.goto('/demo');
      await page.getByTestId('showroom-pick-overloaded_morning').click();
      const { blocking, summary } = await scanThemedPage(
        page,
        testInfo,
        `showroom-ready-${scheme}`
      );
      expect(blocking, summary).toEqual([]);
    });

    test('email decision has no blocking violation', async ({ page }, testInfo) => {
      await page.goto('/demo');
      await walkToEmailDecision(page);
      const { blocking, summary } = await scanThemedPage(
        page,
        testInfo,
        `showroom-email-${scheme}`
      );
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
      const receipt = await scanThemedPage(page, testInfo, `showroom-receipt-${scheme}`);
      expect(receipt.blocking, receipt.summary).toEqual([]);

      await page.getByTestId('showroom-proof-open').click();
      await expect(page.getByRole('dialog')).toBeVisible();
      const drawer = await scanThemedPage(page, testInfo, `showroom-drawer-${scheme}`);
      expect(drawer.blocking, drawer.summary).toEqual([]);
    });

    for (const mission of [
      { id: 'daily_briefing', label: 'Radio', resultSelector: '.lia-steps' },
      { id: 'config_tour', label: 'meeting minutes', resultSelector: '.lia-response h3' },
    ] as const) {
      test(`${mission.label} result has no blocking violation or decision card`, async ({
        page,
      }, testInfo) => {
        await page.goto('/demo');
        await walkToReadOnlyReceipt(page, mission.id);
        // Wait for the production rich renderer, rather than scanning its
        // dynamic-import loading placeholder as a vacuously clean result.
        await expect(
          page.getByTestId('showroom-rich-response').locator(mission.resultSelector).first()
        ).toBeVisible();
        const { blocking, summary } = await scanThemedPage(
          page,
          testInfo,
          `showroom-${mission.id}-receipt-${scheme}`
        );
        expect(blocking, summary).toEqual([]);
      });
    }
  });
}
