/**
 * The landing's catalogs are FOLDED on arrival (owner arbitration 2026-09-24):
 * a guard that measures or scans the page must unfold them first, or the
 * feature cards they hold would be skipped — a collapsed panel is invisible to
 * axe and has no width to overflow with.
 */

import type { Page } from '@playwright/test';

/** Unfold every catalog of the landing; returns how many were folded. */
export async function unfoldCatalogs(page: Page): Promise<number> {
  const unfolded = await page.evaluate(() => {
    const folded = Array.from(
      document.querySelectorAll<HTMLButtonElement>(
        '[id$="-detail"] > button[aria-expanded="false"]'
      )
    );
    folded.forEach(button => button.click());
    return folded.length;
  });
  // The panel opens with a 300 ms grid-template-rows transition.
  await page.waitForTimeout(400);
  return unfolded;
}
