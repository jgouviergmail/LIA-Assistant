/**
 * Settings quick search — typing a name reaches the section.
 *
 * Unit tests pin the matching against the six dictionaries and the combobox
 * contract in jsdom. What only a browser can prove is the chain AFTER the pick:
 * Radix mounts one tab panel at a time, so reaching a Features section from the
 * Preferences tab means a tab switch, a mount, an accordion expansion, a scroll
 * that clears the sticky chrome, and a focus move — none of which jsdom has any
 * notion of.
 *
 * Two things here are not incidental:
 *
 *  1. the query is typed WITHOUT its accent ("memoire" for "Mémoire long
 *     terme"). Diacritic folding is the difference between a search that works
 *     on a French keyboard and one that does not;
 *  2. focus is asserted, not just position. A result picked with the keyboard
 *     must leave the caret on the section — otherwise the next Tab press sends
 *     a keyboard user back to the top of the page.
 */
import { test, expect, type MockRoute } from '../fixtures';

/**
 * Deliberately minimal, same reasoning as `settings-deep-links.spec.ts`: broad
 * patterns shadow the shell mocks (Playwright routes are LIFO) and make the run
 * erratic. Unmocked endpoints hit the 501 catch-all, which every section
 * survives — and the two sections exercised here render unconditionally.
 */
const ROUTES: MockRoute[] = [
  { url: '**/api/v1/connectors', json: { connectors: [] } },
  { url: '**/api/v1/scheduled-actions**', json: { actions: [], total: 0 } },
  { url: '**/api/v1/usage/**', json: {} },
];

/** French labels of the surfaces under test — the suite runs in `fr`. */
const SEARCH_LABEL = 'Rechercher un réglage';

/**
 * Generous, and it is the dev server's cost rather than a product signal: the
 * settings route mounts thirty sections with their own queries, and `next dev`
 * compiles it on demand — the first spec to reach it pays for all of them.
 * Against the CI production build this resolves immediately. Same reasoning,
 * and same number, as `settings-deep-links.spec.ts`; the first assertion of the
 * file gets more because it is the one that pays the cold compile.
 */
const APPEARS = 20_000;
const APPEARS_COLD = 60_000;

test.describe('settings search', () => {
  test('reaches a section of the OTHER tab, expanded and focused', async ({
    page,
    authenticate,
    mockApi,
  }) => {
    await authenticate({ language: 'fr' });
    await mockApi(ROUTES);
    await page.goto('/fr/dashboard/settings');

    const search = page.getByRole('combobox', { name: SEARCH_LABEL });
    await expect(search).toBeVisible({ timeout: APPEARS_COLD });

    // Unaccented on purpose: the section is "Mémoire long terme".
    await search.fill('memoire');

    const listbox = page.getByRole('listbox');
    await expect(listbox).toBeVisible({ timeout: APPEARS });
    await listbox.getByRole('option').first().click();

    // The Features panel is mounted only once its tab is active.
    const section = page.locator('#settings-section-memories');
    await expect(section, 'the picked section must be mounted').toBeAttached({ timeout: APPEARS });
    await expect(section, 'and expanded').toHaveAttribute('data-state', 'open', {
      timeout: APPEARS,
    });
    await expect(page.getByRole('tab', { selected: true })).toHaveText(/Fonctionnalités/);

    // The field is cleared and the popup closed, so a stale query cannot reopen
    // over the section the reader just landed on.
    await expect(search).toHaveValue('');
    await expect(page.getByRole('listbox')).toBeHidden();

    // Focus lands ON the section — and it lands LATE on purpose: the page waits
    // for the accordion to have opened before scrolling and focusing, so a
    // single synchronous read here races the reveal and reports `null` while
    // the caret is about to arrive (measured: it lands ~100 ms after the pick).
    await expect
      .poll(
        () =>
          page.evaluate(
            () => document.activeElement?.closest('[id^="settings-section-"]')?.id ?? null
          ),
        { timeout: APPEARS, message: 'focus never reached the picked section' }
      )
      .toBe('settings-section-memories');

    // …and STAYS there. A re-render that replaced the trigger would drop focus
    // back to the body, which is the failure a single poll would not see.
    await page.waitForTimeout(600);
    const stillFocused = await page.evaluate(
      () => document.activeElement?.closest('[id^="settings-section-"]')?.id ?? null
    );
    expect(stillFocused, 'focus was lost after the section settled').toBe(
      'settings-section-memories'
    );
  });

  test('is entirely operable from the keyboard', async ({ page, authenticate, mockApi }) => {
    await authenticate({ language: 'fr' });
    await mockApi(ROUTES);
    await page.goto('/fr/dashboard/settings');

    const search = page.getByRole('combobox', { name: SEARCH_LABEL });
    await expect(search).toBeVisible({ timeout: APPEARS });

    await search.focus();
    await page.keyboard.type('apparence');
    await expect(page.getByRole('listbox')).toBeVisible({ timeout: APPEARS });

    await page.keyboard.press('ArrowDown');
    // The active option is advertised through aria-activedescendant, not focus:
    // the caret must stay in the field for typing to continue working.
    await expect(search).toHaveAttribute('aria-activedescendant', /settings-search-option-0/);
    await expect(search).toBeFocused();

    await page.keyboard.press('Enter');
    const section = page.locator('#settings-section-theme');
    await expect(section).toHaveAttribute('data-state', 'open', { timeout: APPEARS });
  });

  test('lands the picked section below the sticky chrome', async ({
    page,
    authenticate,
    mockApi,
  }) => {
    await authenticate({ language: 'fr' });
    await mockApi(ROUTES);
    await page.goto('/fr/dashboard/settings');

    const search = page.getByRole('combobox', { name: SEARCH_LABEL });
    await expect(search).toBeVisible({ timeout: APPEARS });
    await search.fill('memoire');
    await page.getByRole('listbox').getByRole('option').first().click();

    const section = page.locator('#settings-section-memories');
    await expect(section).toBeAttached({ timeout: APPEARS });
    // Let the smooth scroll settle before measuring.
    await expect
      .poll(async () => (await section.boundingBox())?.y ?? -1, { timeout: 10_000 })
      .toBeGreaterThan(0);

    const geometry = await page.evaluate(() => {
      const target = document.getElementById('settings-section-memories');
      const bar = document.querySelector('[data-testid="settings-sticky-bar"]');
      if (!target || !bar) return null;
      return {
        sectionTop: Math.round(target.getBoundingClientRect().top),
        barBottom: Math.round(bar.getBoundingClientRect().bottom),
      };
    });

    expect(geometry).not.toBeNull();
    expect(
      geometry!.sectionTop,
      `a searched section landed at ${geometry!.sectionTop}, under a sticky bar ending at ${geometry!.barBottom}`
    ).toBeGreaterThanOrEqual(geometry!.barBottom);
  });

  test('opens a Preferences section for a superuser, whose accordion is a different one', async ({
    page,
    authenticate,
    mockApi,
  }) => {
    // The Preferences panel is driven by TWO different states: a superuser gets
    // its own (`appearanceSections`, because their layout has a third tab),
    // everyone else shares one for the whole tab. Nothing in the browser suite
    // had ever exercised the superuser side of that branch — not before this
    // lot either — so a swapped arm would expand nothing and no test would say
    // so.
    await authenticate({ language: 'fr', is_superuser: true });
    await mockApi(ROUTES);
    await page.goto('/fr/dashboard/settings');

    const search = page.getByRole('combobox', { name: SEARCH_LABEL });
    await expect(search).toBeVisible({ timeout: APPEARS });
    await search.fill('apparence');
    await page.getByRole('listbox').getByRole('option').first().click();

    const section = page.locator('#settings-section-theme');
    await expect(section).toBeAttached({ timeout: APPEARS });
    await expect(section, 'the superuser accordion must expand too').toHaveAttribute(
      'data-state',
      'open',
      { timeout: APPEARS }
    );
    // Three tabs is what makes this layout the superuser one.
    await expect(page.getByRole('tab')).toHaveCount(3);
  });

  test('fits a 320 px screen without pushing anything off it', async ({
    page,
    authenticate,
    mockApi,
  }) => {
    // The field joined a bar that is already tight at 320 px (three tab labels
    // in German fit only because they truncate). A results popup that overflowed
    // would be clipped at the screen edge — silently, the same way the tab
    // labels used to be.
    await authenticate({ language: 'fr', is_superuser: true });
    await mockApi(ROUTES);
    await page.setViewportSize({ width: 320, height: 800 });
    await page.goto('/fr/dashboard/settings');

    const search = page.getByRole('combobox', { name: SEARCH_LABEL });
    await expect(search).toBeVisible({ timeout: APPEARS });
    await search.fill('memoire');
    await expect(page.getByRole('listbox')).toBeVisible({ timeout: APPEARS });

    const report = await page.evaluate(() => {
      const popup = document.querySelector('[role="listbox"]')!.closest('div')!;
      const box = popup.getBoundingClientRect();
      return {
        left: Math.round(box.left),
        right: Math.round(box.right),
        viewport: window.innerWidth,
        documentScrollWidth: document.documentElement.scrollWidth,
      };
    });

    expect(report.left, 'popup starts off-screen').toBeGreaterThanOrEqual(0);
    expect(report.right, 'popup ends past the right edge').toBeLessThanOrEqual(report.viewport);
    // The page itself must not have gained a horizontal scrollbar.
    expect(
      report.documentScrollWidth,
      `document scrolls horizontally (${report.documentScrollWidth} > ${report.viewport})`
    ).toBeLessThanOrEqual(report.viewport);
  });

  test('says so plainly when nothing matches', async ({ page, authenticate, mockApi }) => {
    await authenticate({ language: 'fr' });
    await mockApi(ROUTES);
    await page.goto('/fr/dashboard/settings');

    const search = page.getByRole('combobox', { name: SEARCH_LABEL });
    await expect(search).toBeVisible({ timeout: APPEARS });
    await search.fill('zzzqwerty');

    await expect(page.getByRole('listbox')).toBeHidden();
    // Two elements carry the sentence on purpose — the visible message and the
    // live region — so the locator says which one, rather than the assertion
    // being loosened to "somewhere on the page".
    await expect(
      page.getByRole('paragraph').filter({ hasText: /Aucun réglage ne correspond/ })
    ).toBeVisible();
    // Announced, not merely printed.
    await expect(page.getByRole('status')).toContainText(/Aucun réglage ne correspond/);
  });
});
