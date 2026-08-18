/**
 * The landing header's desktop link row, at its tightest.
 *
 * The row appears at exactly 880px (`--breakpoint-mobile`) and is at its most
 * cramped right there, in whichever locale spells the links longest. It has
 * overflowed before: adding the sixth page link ("Encore +") pushed the French
 * row 25px past a 880–900px viewport, and the fix was to tighten the padding —
 * a fix nothing then guarded. A seventh entry ("Nouveautés" / "What's new")
 * has since joined it, so the measurement belongs in the suite rather than in
 * a comment.
 *
 * The existing landing overflow specs run at 375px and 320px, where this row
 * is `hidden` — they could never have caught it.
 */
import { test, expect } from '../fixtures';

import { awaitStyledPage, expectNoOverflow } from './overflow-report';

const LOCALE_PATHS: ReadonlyArray<readonly [string, string]> = [
  ['fr', '/fr'],
  ['en', '/en'],
  ['de', '/de'],
  ['es', '/es'],
  ['it', '/it'],
  ['zh', '/zh'],
];

test.describe('landing header — the row fits where it first appears (880px)', () => {
  test.use({ viewport: { width: 880, height: 900 }, locale: 'fr-FR' });

  test('every locale keeps the header row inside the viewport', async ({ page }) => {
    for (const [lng, path] of LOCALE_PATHS) {
      await page.goto(path);
      await awaitStyledPage(page, `nav row ${lng}`);
      await expectNoOverflow(page, `${lng} header row at 880px`);
    }
  });

  test('the release entry stays out of the saturated row', async ({ page }) => {
    // Measured: adding it here ran the French row 96px past the viewport. It
    // returns at `lg`; below that the band is reached by scrolling, from the
    // footers, or from the mobile menu.
    await page.goto('/fr');
    await awaitStyledPage(page, 'nav row fr');

    const header = page.getByRole('banner').or(page.locator('header')).first();
    await expect(header.getByRole('link', { name: 'Nouveautés' })).toBeHidden();
    // The band itself is on the page regardless of the header's width.
    await expect(page.locator('#changelog')).toHaveCount(1);
  });
});

test.describe('landing header — the release band, from lg up', () => {
  test.use({ viewport: { width: 1024, height: 900 }, locale: 'fr-FR' });

  test('is listed last and scrolls to the band', async ({ page }) => {
    await page.goto('/fr');
    await awaitStyledPage(page, 'nav row fr at lg');
    await expectNoOverflow(page, 'header row at 1024px');

    const header = page.getByRole('banner').or(page.locator('header')).first();
    const labels = await header.getByRole('link').allInnerTexts();
    // Listed immediately after "Encore +": a visitor reads the product first,
    // its news last (owner arbitration). Asserted as a RELATION rather than a
    // last position — the right-hand actions are links too.
    expect(labels.indexOf('Nouveautés')).toBe(labels.indexOf('Encore +') + 1);

    await header.getByRole('link', { name: 'Nouveautés' }).click();
    const band = page.locator('#changelog');
    await expect(band).toBeVisible();
    // The band quotes releases, and hands the full history back to the FAQ.
    // Scoped: the shuffled blog grid can surface a post whose title also
    // contains the word, and the pick changes between runs.
    await expect(band.getByRole('link', { name: /historique/i })).toBeVisible();
  });
});
