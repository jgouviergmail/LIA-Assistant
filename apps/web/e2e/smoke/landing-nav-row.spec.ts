/**
 * The landing header's desktop link row, at its tightest.
 *
 * Compact navigation remains below 1024px. The desktop row begins at 1024px;
 * release and maps links join it at 1280px. Check every locale at those
 * boundaries, including text spilling from a shrinking flex group.
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

test.describe('landing header — navigation fits at its responsive boundaries', () => {
  test.use({ viewport: { width: 880, height: 900 }, locale: 'fr-FR' });

  for (const [lng, path] of LOCALE_PATHS) {
    test(`${lng} keeps the logo, links and account controls separate`, async ({ page }) => {
      await page.goto(path);
      await awaitStyledPage(page, `nav row ${lng}`);
      for (const width of [880, 1024, 1280]) {
        await page.setViewportSize({ width, height: 900 });
        await expectNoOverflow(page, `${lng} header row at ${width}px`);
        const overlaps = await page
          .locator('header nav > div')
          .first()
          .evaluate(row => {
            const groups = Array.from(row.children)
              .map(element => element.getBoundingClientRect())
              .filter(rect => rect.width > 0 && rect.height > 0);
            return groups.flatMap((left, index) =>
              groups
                .slice(index + 1)
                .filter(right => left.right > right.left && left.left < right.right)
            ).length;
          });
        expect(overlaps, `${lng} header groups at ${width}px`).toBe(0);
        const spills = await page
          .locator('header nav > div')
          .first()
          .evaluate(
            row =>
              Array.from(row.children).flatMap(group => {
                const bounds = group.getBoundingClientRect();
                if (!bounds.width || !bounds.height) return [];
                return Array.from(group.querySelectorAll('a, span')).filter(element => {
                  const rect = element.getBoundingClientRect();
                  return (
                    rect.width > 0 &&
                    rect.height > 0 &&
                    (rect.left < bounds.left - 1 || rect.right > bounds.right + 1)
                  );
                });
              }).length
          );
        expect(spills, `${lng} header content at ${width}px`).toBe(0);
      }
    });
  }

  test('the release entry stays out of the saturated row', async ({ page }) => {
    // Measured: adding it here ran the French row 96px past the viewport. It
    // returns at `xl`; below that the band is reached by scrolling, from the
    // footers, or from the mobile menu.
    await page.goto('/fr');
    await awaitStyledPage(page, 'nav row fr');

    const header = page.getByRole('banner').or(page.locator('header')).first();
    await expect(header.getByRole('link', { name: 'Nouveautés' })).toBeHidden();
    // The maps entry shares the release entry's fate below xl (same saturation).
    await expect(header.getByRole('link', { name: 'Cartes' })).toBeHidden();
    // The band itself is on the page regardless of the header's width.
    await expect(page.locator('#changelog')).toHaveCount(1);
  });
});

test.describe('landing header — the release band, from xl up', () => {
  test.use({ viewport: { width: 1280, height: 900 }, locale: 'fr-FR' });

  test('follows the presentation anchor and scrolls to the band', async ({ page }) => {
    await page.goto('/fr');
    await awaitStyledPage(page, 'nav row fr at xl');
    await expectNoOverflow(page, 'header row at 1280px');

    const header = page.getByRole('banner').or(page.locator('header')).first();
    const labels = await header.getByRole('link').allInnerTexts();
    // Listed immediately after "Présentation" (owner arbitration 2026-08-19,
    // superseding "après Encore +"): the product is introduced, then what just
    // shipped. Asserted as a RELATION rather than a fixed position — the logo
    // and the right-hand account actions are links too.
    expect(labels.indexOf('Nouveautés')).toBe(labels.indexOf('Présentation') + 1);
    // "Cartes" opens the page links, between "Nouveautés" and "Story" (owner
    // arbitration 2026-09-24).
    expect(labels.indexOf('Cartes')).toBe(labels.indexOf('Nouveautés') + 1);
    expect(labels.indexOf('Story')).toBe(labels.indexOf('Cartes') + 1);

    await header.getByRole('link', { name: 'Nouveautés' }).click();
    const band = page.locator('#changelog');
    await expect(band).toBeVisible();
    // The band quotes releases, and hands the full history to `/changelog`
    // (the public FAQ never carried one). Scoped: the shuffled blog grid can
    // surface a post whose title also contains the word, and the pick changes
    // between runs.
    await expect(band.getByRole('link', { name: /historique/i })).toHaveAttribute(
      'href',
      '/changelog'
    );
  });
});
