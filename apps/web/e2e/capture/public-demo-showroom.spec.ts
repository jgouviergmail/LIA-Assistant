/**
 * Guided showroom P0 — reproducible launch-asset capture.
 *
 * Runs only on demand (`task test:e2e:showroom:capture`) in the telemetry-OFF
 * showroom build at 1440x900: records the canonical sub-60s mission video
 * (approve email / refuse calendar), plus proof-drawer and receipt stills.
 * Artifacts land in Playwright's output directory — never committed to Git.
 */

import { expect, test } from '@playwright/test';

test.use({
  viewport: { width: 1440, height: 900 },
  video: { mode: 'on', size: { width: 1440, height: 900 } },
  // French capture (the campaign's canonical locale); the public /demo route
  // localizes from Accept-Language, so pin it for deterministic selectors.
  locale: 'fr-FR',
  // Full motion: the capture shows the real demonstration pacing.
  contextOptions: { reducedMotion: 'no-preference' },
});

test('canonical mission capture with refusal respected', async ({ page }, testInfo) => {
  await page.goto('/demo');
  await page.waitForTimeout(1_000); // let the viewer read the mission picker
  await page.getByTestId('showroom-pick-overloaded_morning').click();
  await page.getByTestId('showroom-start').click();
  // Motion allowed: the storyboard paces itself to the email decision.
  await expect(page.getByTestId('showroom-decision-0')).toBeVisible({
    timeout: 20_000,
  });
  await page.waitForTimeout(1_200); // let the viewer read the draft
  await page.getByTestId('showroom-decision-0').getByRole('button', { name: 'Confirmer' }).click();
  await page.waitForTimeout(1_200);
  await page.getByTestId('showroom-decision-1').getByRole('button', { name: 'Annuler' }).click();
  await expect(page.getByTestId('showroom-receipt')).toBeVisible();
  await page.screenshot({
    path: testInfo.outputPath('showroom-receipt.png'),
    fullPage: true,
  });
  await page.getByTestId('showroom-proof-open').click();
  await expect(page.getByRole('dialog')).toBeVisible();
  await page.screenshot({ path: testInfo.outputPath('showroom-proof.png') });
  await page.keyboard.press('Escape');
  await page.waitForTimeout(800); // clean video tail
});
