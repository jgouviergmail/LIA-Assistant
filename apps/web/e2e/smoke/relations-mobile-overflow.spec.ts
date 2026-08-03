/**
 * Relations — no horizontal overflow on mobile.
 *
 * The landing and `/more` each carry a guard of this kind; Relations became a
 * first-class nav destination in v1.27.1 and had none, while being the densest
 * screen in the product: a card packs an avatar, a truncated name, a peer
 * badge, a dormancy chip, up to three coloured pills and a 44px favourite
 * button, and the 360° panel stacks eight foldable sections over it.
 *
 * Why a dedicated spec rather than the existing 320px reflow check: `html` is
 * `overflow-x: hidden`, so a child whose intrinsic (min-content) width inflates
 * its flex/grid track does NOT produce a scrollbar — the user simply sees text
 * and buttons silently clipped at the screen edge. `expectNoOverflow` is what
 * catches that class; a document-scroll assertion alone cannot.
 *
 * **All six locales.** Overflow is string-length dependent and the app ships in
 * six languages: German compounds ("aus den Favoriten entfernen") and the
 * longer Spanish and Italian labels are exactly where a row that fits in French
 * stops fitting. The landing guard learned this the hard way — its original
 * defect only manifested in French and the English row masked it.
 *
 * 375px (iPhone-class) for the sweep, 320px (WCAG 1.4.10 reflow floor) for the
 * narrowest pass.
 */
import { test, expect } from '../fixtures';
import { relationsData } from '../fixtures/relations';
import { awaitStyledPage, expectNoOverflow } from './overflow-report';


/** Frontend-canonical locale segment (zh, never zh-CN — ADR: backend is zh-CN). */
const LOCALES = ['fr', 'en', 'de', 'es', 'it', 'zh'] as const;

/** Open the relationship card of the person the fixture describes in full. */
async function openGerard(page: import('@playwright/test').Page) {
  await page
    .getByRole('main')
    .getByRole('button')
    .filter({ hasText: 'Gérard Dupont' })
    .first()
    .click();
  await expect(page.getByRole('heading', { level: 2, name: 'Gérard Dupont' })).toBeVisible({
    timeout: 15_000,
  });
}

/** Open every folded section, so the widest content is actually on screen. */
async function unfoldEverything(page: import('@playwright/test').Page) {
  // Scoped to `main`: the header's own menus also carry `aria-expanded` and
  // the loop would open and close one forever.
  const collapsed = page.getByRole('main').getByRole('button', { expanded: false });
  for (let guard = 0; guard < 20 && (await collapsed.count()) > 0; guard += 1) {
    await collapsed.first().click();
  }
  expect(await collapsed.count()).toBe(0);
}

test.describe('relations — no horizontal overflow on mobile', () => {
  test.use({ viewport: { width: 375, height: 812 } });

  for (const lng of LOCALES) {
    test(`stays within 375px on the list and the 360° card @ ${lng}`, async ({
      page,
      authenticate,
      mockApi,
    }) => {
      await authenticate();
      await mockApi(relationsData);
      await page.goto(`/${lng}/dashboard/relations`);
      await awaitStyledPage(page, `relations list (${lng})`);

      // The toolbar only appears past a threshold; the fixture carries enough
      // people to bring out the search field, the sort select and the chips.
      await expectNoOverflow(page, `relations list @375 (${lng})`);

      await openGerard(page);
      // FOLDED first: every section is a heading row here, and a heading row
      // carrying a title plus an exact-count badge is what overflows.
      await expectNoOverflow(page, `relations card folded @375 (${lng})`);

      await unfoldEverything(page);
      // Then the widest content the product can show: a postal address that
      // must wrap on its spaces and a URL that cannot wrap at all.
      await expectNoOverflow(page, `relations card unfolded @375 (${lng})`);
    });
  }
});

test.describe('relations — reflow floor', () => {
  test.use({ viewport: { width: 320, height: 800 } });

  test('stays within 320px with every section open (fr)', async ({
    page,
    authenticate,
    mockApi,
  }) => {
    await authenticate();
    await mockApi(relationsData);
    await page.goto('/fr/dashboard/relations');
    await awaitStyledPage(page, 'relations list (320)');

    await expectNoOverflow(page, 'relations list @320');
    await openGerard(page);
    await unfoldEverything(page);
    await expectNoOverflow(page, 'relations card unfolded @320');
  });
});
