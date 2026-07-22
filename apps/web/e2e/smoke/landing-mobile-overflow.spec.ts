/**
 * Landing page mobile horizontal-overflow guard.
 *
 * Regression context (2026-07): three defects clipped landing content on
 * phones, all through the same mechanism — a flex/grid child whose intrinsic
 * (min-content) width inflated its grid track past the viewport:
 *  - the hero badge row (`whitespace-nowrap` version pill in a no-wrap flex),
 *  - the hero mockup's typing input (`truncate` without `min-w-0`), which made
 *    the whole hero column oscillate between 381px and 448px DURING the
 *    animation cycle (invisible on a static screenshot),
 *  - the chapter-01 vignette chip row + truncated query pill (track at 412px).
 * Because `html` is `overflow-x: hidden`, users saw silently clipped text and
 * buttons, not a scrollbar.
 *
 * This spec therefore asserts the invariant at 375px in three ways:
 *  1. statically after load,
 *  2. across the WHOLE hero animation cycle (~79s of virtual time via the
 *     Playwright clock — the mockup timeline is setTimeout-driven),
 *  3. after scrolling through every section (chapter vignettes stage on
 *     intersection).
 * A final static pass runs at 320px (WCAG 1.4.10 reflow floor).
 *
 * Animations are deliberately ENABLED (reducedMotion: no-preference overrides
 * the config default): the oscillation only exists with the timeline running.
 */
import type { Page } from '@playwright/test';
import { test, expect } from '../fixtures';

interface OverflowReport {
  viewportWidth: number;
  documentScrollWidth: number;
  offenders: Array<{ tag: string; cls: string; right: number; text: string }>;
}

/**
 * Report every layout-positioned element whose border box crosses the right
 * viewport edge. Absolutely/fixed-positioned elements are excluded on purpose:
 * the decorative hero glows bleed outside by design and are clipped by their
 * `overflow-hidden` section — they never create scroll or clip content.
 */
async function overflowReport(page: Page): Promise<OverflowReport> {
  return page.evaluate(() => {
    const vw = document.documentElement.clientWidth;
    const offenders: OverflowReport['offenders'] = [];
    document.querySelectorAll<HTMLElement>('body *').forEach(el => {
      const rect = el.getBoundingClientRect();
      if (rect.width === 0 || rect.right <= vw + 1) return;
      const cs = getComputedStyle(el);
      if (cs.position === 'absolute' || cs.position === 'fixed') return;
      offenders.push({
        tag: el.tagName,
        cls: (el.getAttribute('class') ?? '').slice(0, 80),
        right: Math.round(rect.right),
        text: (el.textContent ?? '').slice(0, 40),
      });
    });
    return {
      viewportWidth: vw,
      documentScrollWidth: document.documentElement.scrollWidth,
      offenders: offenders.slice(0, 12),
    };
  });
}

async function expectNoOverflow(page: Page, phase: string): Promise<void> {
  const report = await overflowReport(page);
  expect
    .soft(
      report.offenders,
      `${phase}: elements past the right edge\n${JSON.stringify(report.offenders, null, 2)}`
    )
    .toHaveLength(0);
  expect(
    report.documentScrollWidth,
    `${phase}: document scrolls horizontally (${report.documentScrollWidth}px for ${report.viewportWidth}px viewport)`
  ).toBeLessThanOrEqual(report.viewportWidth);
}

test.describe('landing page — no horizontal overflow on mobile', () => {
  test.use({
    viewport: { width: 375, height: 812 },
    contextOptions: { reducedMotion: 'no-preference' },
  });

  test('stays within 375px through the full hero animation cycle', async ({ page }) => {
    // The mockup timeline is pure setTimeout — the clock drives it through a
    // whole 4-act cycle in milliseconds of real time.
    await page.clock.install();
    await page.goto('/');
    await page.waitForLoadState('networkidle');
    // Fallback-font metrics differ enough to fake overflows — wait for Inter.
    await page.evaluate(() => document.fonts.ready);

    await expectNoOverflow(page, 'initial render');

    // One full cycle is ~79s (4 scenarios, holdMs + fade each). Step in 2s
    // beats and assert at every beat so any act/backstage state that inflates
    // the layout is caught, not just the ones a screenshot happens to hit.
    for (let beat = 1; beat <= 40; beat++) {
      await page.clock.runFor(2_000);
      await expectNoOverflow(page, `animation beat ${beat} (t=${beat * 2}s)`);
    }
  });

  test('stays within 375px across all scrolled sections', async ({ page }) => {
    await page.goto('/');
    await page.waitForLoadState('networkidle');
    await page.evaluate(() => document.fonts.ready);

    const sectionIds = await page.evaluate(() =>
      Array.from(document.querySelectorAll('section[id], div#features section'), s => s.id).filter(
        Boolean
      )
    );
    expect(sectionIds.length).toBeGreaterThanOrEqual(10);

    for (const id of sectionIds) {
      await page.evaluate(sectionId => {
        document.getElementById(sectionId)?.scrollIntoView();
      }, id);
      // Let the one-shot stage/fade-in observers fire and settle.
      await page.waitForTimeout(700);
      await expectNoOverflow(page, `section #${id}`);
    }
  });
});

test.describe('landing page — WCAG reflow floor', () => {
  test.use({ viewport: { width: 320, height: 700 } });

  test('renders without horizontal overflow at 320px', async ({ page }) => {
    await page.goto('/');
    await page.waitForLoadState('networkidle');
    await page.evaluate(() => document.fonts.ready);
    await expectNoOverflow(page, '320px initial render');
  });
});
