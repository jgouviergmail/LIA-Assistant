/**
 * The composer stays inside the viewport (S2).
 *
 * The chat shell is sized from the viewport height minus the header. When that
 * arithmetic is wrong — or based on the LARGE viewport (`100vh`) while the
 * browser's URL bar is on screen — the bottom of the shell, i.e. the composer,
 * falls below the fold: the user has to scroll the page to reach the one
 * control the screen exists for.
 *
 * Headless Chromium has no retractable URL bar, so `dvh` and `vh` resolve to
 * the same number here; this spec therefore does NOT prove the `dvh` switch by
 * itself (a real device would). What it does prove is the invariant the switch
 * protects — the composer is reachable without scrolling — and it locks the
 * page-level arithmetic so a future layout change cannot quietly push the
 * composer out at any of the widths S0 measured.
 */
import type { Locator, Page } from '@playwright/test';

import { test, expect, type MockRoute } from '../fixtures';

/**
 * Wait until an element's box stops moving.
 *
 * Against the dev server the first paint of a route can land before layout has
 * settled (on-demand compilation, fonts, async shell widgets). Measuring then
 * produced a first-run-only failure — the very definition of a flaky guard.
 * Polling until two consecutive readings agree makes the measurement depend on
 * the layout rather than on the timing.
 */
async function waitForStableBox(page: Page, locator: Locator): Promise<void> {
  let previous = '';
  for (let attempt = 0; attempt < 20; attempt++) {
    const box = await locator.boundingBox();
    const current = box ? `${Math.round(box.y)}:${Math.round(box.height)}` : '';
    if (current !== '' && current === previous) return;
    previous = current;
    await page.waitForTimeout(100);
  }
}

const WIDTHS = [320, 390, 768, 1280] as const;
const HEIGHTS = [640, 800] as const;

const ROUTES: MockRoute[] = [
  {
    url: '**/api/v1/conversations/me/messages*',
    json: {
      messages: [],
      conversation_id: null,
      total_count: 0,
      has_more: false,
      next_cursor: null,
    },
  },
  { url: '**/api/v1/conversations/me/totals', json: {} },
  { url: '**/api/v1/agents/health', json: { status: 'healthy', graph_compiled: true } },
  { url: '**/api/v1/agents/runs/active', json: { active: false } },
  { url: '**/api/v1/agents/hitl/pending', json: null },
  { url: '**/api/v1/usage/**', json: {} },
];

test.describe('chat composer reachability', () => {
  test('the composer is fully visible without scrolling, at every size', async ({
    page,
    authenticate,
    mockApi,
  }) => {
    await authenticate({ language: 'fr' });
    await mockApi(ROUTES);
    await page.goto('/fr/dashboard/chat');
    const composer = page.locator('textarea').first();
    await composer.waitFor({ state: 'visible' });

    for (const width of WIDTHS) {
      for (const height of HEIGHTS) {
        await page.setViewportSize({ width, height });
        await page.waitForFunction(
          ([w, h]) =>
            document.documentElement.clientWidth === w &&
            document.documentElement.clientHeight === h,
          [width, height] as const
        );
        await waitForStableBox(page, composer);

        expect(
          await composer.boundingBox(),
          `${width}x${height}: composer must be laid out`
        ).not.toBeNull();

        // Bottom edge inside the viewport.
        //
        // Polled: `waitForStableBox` settles the COMPOSER's own box, which can
        // stop moving while the header is still reflowing above it (measured:
        // a 65 px gap at 320 px, exactly the header's height, on a read taken
        // mid-reflow). The invariant is unchanged — it is simply allowed to
        // settle first.
        await expect
          .poll(
            async () => {
              const current = await composer.boundingBox();
              return current ? Math.round(current.y + current.height) : Number.NaN;
            },
            { message: `${width}x${height}: composer bottom is below the fold` }
          )
          .toBeLessThanOrEqual(height);

        // …and the page itself must not have grown a vertical scrollbar to
        // make that possible (that would just move the problem).
        const pageOverflow = await page.evaluate(() => {
          const el = document.scrollingElement ?? document.documentElement;
          return el.scrollHeight - el.clientHeight;
        });
        expect(
          pageOverflow,
          `${width}x${height}: the page scrolls, so the shell exceeds the viewport`
        ).toBeLessThanOrEqual(1);
      }
    }
  });

  test('the shell height tracks the dynamic viewport unit', async ({
    page,
    authenticate,
    mockApi,
  }) => {
    // Pins the declaration itself: the computed height must come from the
    // dvh-based rule, not from the `vh` fallback that precedes it. Resolving
    // `100dvh` in the page and comparing proves which rule won.
    await authenticate({ language: 'fr' });
    await mockApi(ROUTES);
    await page.setViewportSize({ width: 390, height: 800 });
    await page.goto('/fr/dashboard/chat');
    const composer = page.locator('textarea').first();
    await composer.waitFor({ state: 'visible' });
    await waitForStableBox(page, composer);

    // Polled, not sampled once: `waitForStableBox` above settles the COMPOSER,
    // which reaches its final box before the shell does (the thread mounts
    // after it). A single read caught the shell mid-layout and compared a
    // transient height. The assertion is unchanged — only its patience is.
    //
    // 5.25rem = 84 px of header chrome subtracted by the shell rule.
    await expect
      .poll(
        async () =>
          page.evaluate(() => {
            const shell = document.querySelector('[class*="calc(100vh"]');
            const probe = document.createElement('div');
            probe.style.cssText =
              'position:absolute;height:100dvh;visibility:hidden;pointer-events:none';
            document.body.appendChild(probe);
            const dynamic = probe.getBoundingClientRect().height;
            probe.remove();
            const shellHeight = shell ? Math.round(shell.getBoundingClientRect().height) : 0;
            return shellHeight - Math.round(dynamic);
          }),
        { message: 'the shell must resolve its height from the dvh rule' }
      )
      .toBe(-84);
  });
});
