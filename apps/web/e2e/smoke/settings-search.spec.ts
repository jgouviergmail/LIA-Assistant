/**
 * Settings quick search — typing a name reaches the section.
 *
 * Unit tests pin the matching against the six dictionaries and the combobox
 * contract in jsdom. What only a browser can prove is the chain AFTER the
 * pick: the pane mounts the section, the page scrolls back to the top, and
 * focus lands ON the section card — otherwise the next Tab press sends a
 * keyboard user back to the top of the page.
 *
 * Two things here are not incidental:
 *
 *  1. the query is typed WITHOUT its accent ("memoire" for "Mémoire long
 *     terme"). Diacritic folding is the difference between a search that works
 *     on a French keyboard and one that does not;
 *  2. the administration coverage is asserted for a superuser (phase 2 of
 *     ADR-172) AND its absence for a regular account — the same search must
 *     not advertise panes the reader cannot open.
 */
import { test, expect, type MockRoute } from '../fixtures';

/**
 * Deliberately minimal, same reasoning as `settings-deep-links.spec.ts`: broad
 * patterns shadow the shell mocks (Playwright routes are LIFO) and make the run
 * erratic. Unmocked endpoints hit the 501 catch-all, which every section
 * survives — and the sections exercised here render unconditionally.
 */
const ROUTES: MockRoute[] = [
  { url: '**/api/v1/connectors', json: { connectors: [] } },
  { url: '**/api/v1/scheduled-actions**', json: { actions: [], total: 0 } },
  { url: '**/api/v1/usage/**', json: {} },
];

/** French labels of the surfaces under test — the suite runs in `fr`. */
const SEARCH_LABEL = 'Rechercher un réglage';

/**
 * Generous, and it is the dev server's cost rather than a product signal:
 * `next dev` compiles the route on demand — the first spec to reach it pays
 * for it. Against the CI production build this resolves immediately.
 */
const APPEARS = 20_000;
const APPEARS_COLD = 60_000;

test.describe('settings search', () => {
  test('reaches a section, mounted and focused', async ({ page, authenticate, mockApi }) => {
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

    const section = page.locator('#settings-section-memories');
    await expect(section, 'the picked section must be mounted').toBeVisible({ timeout: APPEARS });

    // The field is cleared and the popup closed, so a stale query cannot
    // reopen over the section the reader just landed on.
    await expect(search).toHaveValue('');
    await expect(page.getByRole('listbox')).toBeHidden();

    // Focus lands ON the section card — and it lands LATE on purpose: the pane
    // waits for the section to have settled before focusing, so a single
    // synchronous read here races the reveal.
    await expect
      .poll(
        () =>
          page.evaluate(
            () => document.activeElement?.closest('[id^="settings-section-"]')?.id ?? null
          ),
        { timeout: APPEARS, message: 'focus never reached the picked section' }
      )
      .toBe('settings-section-memories');

    // …and STAYS there. A re-render that replaced the card would drop focus
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
    await expect(page.locator('#settings-section-theme')).toBeVisible({ timeout: APPEARS });
  });

  test('lands the reader at the top of the opened pane', async ({
    page,
    authenticate,
    mockApi,
  }) => {
    await authenticate({ language: 'fr' });
    await mockApi(ROUTES);
    await page.goto('/fr/dashboard/settings');

    const search = page.getByRole('combobox', { name: SEARCH_LABEL });
    await expect(search).toBeVisible({ timeout: APPEARS });
    // Scroll deep into the overview first, so "back to the top" is observable.
    await page.mouse.wheel(0, 2000);
    await expect.poll(() => page.evaluate(() => window.scrollY)).toBeGreaterThan(0);

    await search.fill('memoire');
    await page.getByRole('listbox').getByRole('option').first().click();

    await expect(page.locator('#settings-section-memories')).toBeVisible({ timeout: APPEARS });
    await expect
      .poll(() => page.evaluate(() => window.scrollY), { timeout: 10_000 })
      .toBe(0);
  });

  test('finds an administration pane for a superuser, and opens it', async ({
    page,
    authenticate,
    mockApi,
  }) => {
    // Phase 2 of ADR-172: the administration sections joined the index. This
    // is the journey that did not exist before the master-detail shell.
    await authenticate({ language: 'fr', is_superuser: true });
    await mockApi(ROUTES);
    await page.goto('/fr/dashboard/settings');

    const search = page.getByRole('combobox', { name: SEARCH_LABEL });
    await expect(search).toBeVisible({ timeout: APPEARS });
    await search.fill('administration des utilisateurs');

    const listbox = page.getByRole('listbox');
    await expect(listbox).toBeVisible({ timeout: APPEARS });
    await listbox.getByRole('option').first().click();

    await expect(page.locator('#settings-section-admin-users')).toBeVisible({ timeout: APPEARS });
    expect(new URL(page.url()).searchParams.get('section')).toBe('admin-users');
  });

  test('never offers the administration panes to a regular account', async ({
    page,
    authenticate,
    mockApi,
  }) => {
    await authenticate({ language: 'fr' });
    await mockApi(ROUTES);
    await page.goto('/fr/dashboard/settings');

    const search = page.getByRole('combobox', { name: SEARCH_LABEL });
    await expect(search).toBeVisible({ timeout: APPEARS });
    await search.fill('administration des utilisateurs');

    // The all-words tier may legitimately surface a USER section containing
    // these common words; what must never appear is the admin pane itself.
    await expect(page.getByRole('status')).toContainText(/./, { timeout: APPEARS });
    await expect(
      page.getByRole('option', { name: /Administration des utilisateurs/ })
    ).toHaveCount(0);
  });

  test('fits a 320 px screen without pushing anything off it', async ({
    page,
    authenticate,
    mockApi,
  }) => {
    // At 320 px the search sits at the top of the drill-down rail. A results
    // popup that overflowed would be clipped at the screen edge — silently.
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
