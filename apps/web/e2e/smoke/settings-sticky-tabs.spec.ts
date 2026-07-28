/**
 * Settings tab bar — persistent, legible, and never hiding what it points at.
 *
 * The settings page stacks ~30 accordion sections over two or three tabs. Once
 * the reader is a few screens down the tabs used to be gone: no way to tell
 * which tab was open, and switching meant scrolling all the way back.
 *
 * Three invariants, none of which a unit test can reach:
 *
 *  1. The bar STICKS. This is the one that silently did not work: `body` was a
 *     scroll container (`overflow-x: hidden` forces `overflow-y` to compute to
 *     `auto`), so no descendant could ever stick — the dashboard header itself
 *     scrolled away while claiming `position: sticky`. See ADR-171. A guard
 *     built on anything but a real scroll would have kept reporting success.
 *
 *  2. Tabs share the row in EQUAL parts and no label escapes its button. Three
 *     equal columns need 422 px (de) to 488 px (it) while a 390 px phone offers
 *     358 px, so `whitespace-nowrap` used to push the label past its own tab
 *     and the overflow was clipped at the screen edge — invisible, and pinning
 *     it to the screen would have made it permanent. Truncation inside the tab
 *     is the accepted trade-off for equal shares; spilling OUT of it is not.
 *
 *  3. A deep-linked section lands BELOW the sticky chrome. `scrollIntoView`
 *     puts the target at the top of the viewport — underneath the header and
 *     the bar — unless `scroll-margin-top` accounts for both. This worked by
 *     accident before ADR-171, when nothing was sticky.
 */
import type { Page } from '@playwright/test';

import { test, expect, type MockRoute } from '../fixtures';

/**
 * Refuse to measure an unstyled page.
 *
 * `next dev` compiles style chunks on demand and, under load, occasionally
 * serves a document whose stylesheet never lands. Every geometric assertion
 * below would then read UA defaults: labels would "overlap" because the flex
 * row does not exist yet. Same doctrine as `a11y/scan.ts` — fail loudly with an
 * actionable message rather than report a layout defect that is not one.
 */
async function waitForStyles(page: Page, label: string): Promise<void> {
  await page
    .waitForFunction(
      () =>
        getComputedStyle(document.documentElement).getPropertyValue('--color-background').trim() !==
        '',
      undefined,
      { timeout: 30_000 }
    )
    .catch(() => {
      throw new Error(
        `layout measurement aborted on ${label}: the app stylesheet never applied ` +
          '(design-system tokens unresolved after 30s) — the server under test is ' +
          'degraded (next dev compiling or broken). An unstyled page has no flex row, ' +
          'so tabs would appear to overlap. Restart the dev server and re-run.'
      );
    });
}

/**
 * Deliberately minimal — same reasoning as `settings-deep-links.spec.ts`: broad
 * patterns shadow the shell mocks (Playwright routes are LIFO) and make the run
 * erratic. Unmocked endpoints hit the 501 catch-all, which every section is
 * built to survive.
 */
const ROUTES: MockRoute[] = [
  { url: '**/api/v1/connectors', json: { connectors: [] } },
  { url: '**/api/v1/scheduled-actions**', json: { actions: [], total: 0 } },
  { url: '**/api/v1/usage/**', json: {} },
];

/** Locales carrying the longest tab labels — the ones that break first. */
const NARROW_LOCALES = ['de', 'it', 'es'] as const;

test.describe('settings tab bar', () => {
  test('stays visible once the page is scrolled', async ({ page, authenticate, mockApi }) => {
    await authenticate({ language: 'fr' });
    await mockApi(ROUTES);
    await page.goto('/fr/dashboard/settings');
    await waitForStyles(page, '/dashboard/settings');

    const tablist = page.getByRole('tablist');
    await expect(tablist).toBeVisible({ timeout: 20_000 });

    const before = await tablist.boundingBox();
    expect(before).not.toBeNull();

    await page.evaluate(() => window.scrollTo(0, 1200));
    // Two frames: the sticky offset is resolved during layout, not on the
    // scroll event.
    await page.evaluate(
      () => new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve)))
    );

    const scrollY = await page.evaluate(() => window.scrollY);
    expect(scrollY, 'the page must actually scroll for this to prove anything').toBeGreaterThan(
      400
    );

    await expect(tablist, 'the tab bar must survive the scroll').toBeVisible();
    const after = await tablist.boundingBox();
    expect(after).not.toBeNull();
    // Stuck under the 64 px header — NOT carried away with the document.
    expect(
      after!.y,
      `tab bar drifted to y=${after!.y} after scrolling ${scrollY}px (before: ${before!.y})`
    ).toBeLessThan(140);
    expect(after!.y).toBeGreaterThanOrEqual(0);
  });

  for (const locale of NARROW_LOCALES) {
    test(`shares the row equally and keeps labels inside their tab at 320 px @ ${locale}`, async ({
      page,
      authenticate,
      mockApi,
    }) => {
      await authenticate({ language: locale, is_superuser: true });
      await mockApi(ROUTES);
      await page.setViewportSize({ width: 320, height: 800 });
      await page.goto(`/${locale}/dashboard/settings`);
      await waitForStyles(page, `/dashboard/settings @${locale}`);
      await expect(page.getByRole('tablist')).toBeVisible({ timeout: 20_000 });

      const report = await page.evaluate(() => {
        const list = document.querySelector<HTMLElement>('[role="tablist"]');
        const tabs = Array.from(document.querySelectorAll<HTMLElement>('[role="tab"]'));
        if (!list) return { count: 0, widths: [], spilling: [], outside: ['no tablist'] };

        // 1. Equal shares — the whole point of the grid layout.
        const widths = tabs.map(tab => Math.round(tab.getBoundingClientRect().width));

        // 2. No label spills OUT of its tab. This is the discriminating one:
        //    with equal columns the label keeps its intrinsic width unless it
        //    is allowed to shrink, and simply runs past the button's box —
        //    falsified against the pre-fix layout, which reported
        //    "Einstellungen" spilling while this one reports nothing.
        const spilling = tabs
          .map(tab => {
            const label = tab.querySelector('span') ?? tab;
            const l = label.getBoundingClientRect();
            const t = tab.getBoundingClientRect();
            return {
              text: (tab.textContent ?? '').trim(),
              past: Math.round(Math.max(l.right - t.right, t.left - l.left)),
            };
          })
          .filter(x => x.past > 1);

        // 3. Every tab sits inside the list's box — nothing clipped at the edge.
        const outside: string[] = [];
        const lb = list.getBoundingClientRect();
        for (const tab of tabs) {
          const t = tab.getBoundingClientRect();
          if (t.left < lb.left - 1 || t.right > lb.right + 1) {
            outside.push(
              `${(tab.textContent ?? '').trim()} (${Math.round(t.right - lb.right)}px past)`
            );
          }
        }
        return { count: tabs.length, widths, spilling, outside };
      });

      expect(report.count, 'a superuser has three tabs').toBe(3);
      // Equal shares: rounding may differ by a pixel, nothing more.
      const spread = Math.max(...report.widths) - Math.min(...report.widths);
      expect(spread, `tab widths must be equal, got ${report.widths.join(' / ')}px`).toBeLessThanOrEqual(1);
      expect(
        report.spilling,
        `labels spilling out of their tab: ${report.spilling
          .map(t => `${t.text} (+${t.past}px)`)
          .join(', ')}`
      ).toEqual([]);
      expect(report.outside, `tabs clipped by the list: ${report.outside.join(' | ')}`).toEqual([]);
    });
  }

  test('a deep-linked section lands below the sticky chrome, not under it', async ({
    page,
    authenticate,
    mockApi,
  }) => {
    await authenticate({ language: 'fr' });
    await mockApi(ROUTES);
    await page.goto('/fr/dashboard/settings?section=voice-mode');
    await waitForStyles(page, '/dashboard/settings?section=voice-mode');

    const section = page.locator('#settings-section-voice-mode');
    await expect(section).toBeAttached({ timeout: 20_000 });
    await expect(section).toHaveAttribute('data-state', 'open', { timeout: 10_000 });

    // Let the smooth scroll settle before measuring.
    await expect
      .poll(async () => (await section.boundingBox())?.y ?? -1, { timeout: 10_000 })
      .toBeGreaterThan(0);

    const geometry = await page.evaluate(() => {
      const target = document.getElementById('settings-section-voice-mode');
      // The sticky CONTAINER, not the tab list inside it. The bar now carries a
      // second row — the settings search — under the tabs, so the tab list's
      // bottom edge is no longer the bottom of the sticky chrome: measuring it
      // would report success while the section sat under the search field.
      const bar = document.querySelector('[data-testid="settings-sticky-bar"]');
      const tablist = document.querySelector('[role="tablist"]');
      if (!target || !bar || !tablist) return null;
      return {
        sectionTop: Math.round(target.getBoundingClientRect().top),
        barBottom: Math.round(bar.getBoundingClientRect().bottom),
        tablistBottom: Math.round(tablist.getBoundingClientRect().bottom),
      };
    });

    expect(geometry).not.toBeNull();
    // Falsification of the measurement itself: if these two were equal, the
    // assertion below would be the old, weaker one without anybody noticing.
    expect(
      geometry!.barBottom,
      'the sticky bar must extend below the tab list — otherwise the search row is missing and this test is measuring the wrong thing'
    ).toBeGreaterThan(geometry!.tablistBottom);
    expect(
      geometry!.sectionTop,
      `section top (${geometry!.sectionTop}) must clear the whole sticky bar (${geometry!.barBottom}), tab list ends at ${geometry!.tablistBottom}`
    ).toBeGreaterThanOrEqual(geometry!.barBottom);
  });
});
