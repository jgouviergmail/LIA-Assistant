/**
 * Shared horizontal-overflow measurement for public-page smoke specs
 * (landing + /more). Extracted verbatim from landing-mobile-overflow.spec.ts.
 *
 * Regression context (2026-07): flex/grid children whose intrinsic
 * (min-content) width inflates a track past the viewport get silently
 * clipped (html is overflow-x hidden), sometimes only DURING an animation
 * frame — hence the per-beat assertions in the callers.
 */

import type { Page } from '@playwright/test';

import { expect } from '../fixtures';

export interface OverflowReport {
  viewportWidth: number;
  documentScrollWidth: number;
  offenders: Array<{ tag: string; cls: string; right: number; text: string }>;
}

/**
 * Report every layout-positioned element whose border box crosses the right
 * viewport edge AND is actually cut at the screen boundary for the user.
 *
 * Two exclusions, both deliberate:
 * - Absolutely/fixed-positioned elements: decorative glows bleed outside by
 *   design and are clipped by their `overflow-hidden` section.
 * - Elements clipped by an ancestor whose own right edge sits WELL INSIDE the
 *   viewport (design truncation — e.g. a mockup input bar `truncate`s its
 *   typing text). The defect this guard exists for is the opposite case:
 *   content cut AT the viewport edge — an element only counts when every
 *   clipping ancestor reaches the screen edge.
 */
export async function overflowReport(page: Page): Promise<OverflowReport> {
  return page.evaluate(() => {
    const vw = document.documentElement.clientWidth;
    const CLIPPING = new Set(['hidden', 'clip', 'auto', 'scroll']);
    const offenders: OverflowReport['offenders'] = [];
    document.querySelectorAll<HTMLElement>('body *').forEach(el => {
      const rect = el.getBoundingClientRect();
      if (rect.width === 0 || rect.right <= vw + 1) return;
      const cs = getComputedStyle(el);
      if (cs.position === 'absolute' || cs.position === 'fixed') return;
      // Nearest clipping boundary: the smallest right edge among ancestors
      // that clip on the x axis. Infinity when nothing clips.
      let clipRight = Infinity;
      for (let node = el.parentElement; node; node = node.parentElement) {
        if (CLIPPING.has(getComputedStyle(node).overflowX)) {
          clipRight = Math.min(clipRight, node.getBoundingClientRect().right);
        }
      }
      // Clipped by an internal container that ends inside the viewport:
      // invisible by design, no content reaches the screen edge.
      if (clipRight < vw - 2) return;
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

/**
 * `next dev` can serve a fresh context an UNSTYLED page (the CSS chunk never
 * applies — documented in ../README.md and guarded the same way by
 * a11y/scan.ts). Without the stylesheet there is no flex, no padding, no
 * min-w-0 — nothing can overflow, so every scan would pass vacuously green.
 * Geometry is the subject under test here: require the design-system tokens
 * before any measurement, and fail loudly if they never resolve.
 */
export async function awaitStyledPage(page: Page, label: string): Promise<void> {
  await page.waitForLoadState('networkidle');
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
        `overflow scan aborted on ${label}: the app stylesheet never applied ` +
          '(design-system tokens unresolved after 30s) — the server under test ' +
          'is degraded (next dev compiling or broken). An unstyled page cannot ' +
          'overflow, so results would be vacuously green. Restart the dev ' +
          'server (purge .next if it keeps returning 500) and re-run.'
      );
    });
  // Fallback-font metrics differ enough to fake overflows — wait for fonts.
  await page.evaluate(() => document.fonts.ready);
}

export async function expectNoOverflow(page: Page, phase: string): Promise<void> {
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
