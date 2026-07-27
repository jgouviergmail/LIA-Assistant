/**
 * Dashboard header — every control stays REACHABLE at every width.
 *
 * Regression context (2026-07-26, measured): the authenticated header packs a
 * logo, four nav links and six controls next to a logout button. At 768 px and
 * 880 px the row overflowed its container and the trailing controls — language
 * selector, personality selector and the LOGOUT button — were pushed past the
 * right edge of the viewport. In German the logout button sat 235 px outside
 * the screen: a signed-in user on a tablet simply could not sign out.
 *
 * Why nothing caught it: `html { overflow-x: hidden }` (globals.css) clips the
 * overflow instead of producing a document scroll, so the existing
 * `scrollWidth - clientWidth` reflow guard reports ZERO at every width (108/108
 * samples). A guard built on document scroll is structurally blind to this
 * class of defect — it must compare each control's box against the viewport.
 *
 * This spec therefore asserts, per width and per locale, that:
 *  1. no header control extends past the viewport's right edge, and
 *  2. no two controls overlap each other (an absolutely-positioned element can
 *     cover another without ever producing overflow).
 *
 * German and Italian are included on purpose: they carry the longest nav labels
 * ("Einstellungen", "Impostazioni") and are the first to break.
 */
import type { Page } from '@playwright/test';

import { test, expect, type MockRoute } from '../fixtures';

/** Widths that matter: the reflow floor, a common phone, and the tablet/split
 *  band where the nav and the control labels are shown SIMULTANEOUSLY. */
const WIDTHS = [320, 390, 768, 880, 1024, 1280] as const;
const LOCALES = ['en', 'fr', 'de', 'es', 'it', 'zh'] as const;

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

interface HeaderProbe {
  clipped: Array<{ name: string; overflowPx: number }>;
  overlaps: string[];
}

/**
 * Wait until the header stops moving before measuring.
 *
 * Several header controls settle asynchronously — the personality selector
 * swaps a "loading" placeholder for the emoji + title, which changes its
 * width. Measuring during that swap produced a flaky overlap. Rather than
 * waiting on one specific control (brittle, and it would hide a future
 * control with the same behaviour), poll the geometry until two consecutive
 * readings agree.
 */
async function waitForStableHeader(page: Page): Promise<void> {
  const signature = () =>
    page.evaluate(() => {
      const header = document.querySelector('header');
      if (!header) return '';
      return Array.from(header.querySelectorAll('a, button'))
        .map(el => {
          const r = el.getBoundingClientRect();
          return `${Math.round(r.x)}:${Math.round(r.width)}`;
        })
        .join('|');
    });

  let previous = await signature();
  for (let attempt = 0; attempt < 20; attempt++) {
    await page.waitForTimeout(100);
    const current = await signature();
    if (current === previous && current !== '') return;
    previous = current;
  }
}

/**
 * Measure the header's interactive controls against the viewport.
 *
 * Only LEAF controls are considered (links and buttons): the flex wrappers are
 * elastic by design and their boxes carry no user-facing meaning. A control is
 * "clipped" when its right edge sits past the viewport — with `overflow-x:
 * hidden` on the root, that is exactly the cut the user sees.
 */
async function probeHeader(page: Page): Promise<HeaderProbe> {
  return page.evaluate(() => {
    const header = document.querySelector('header');
    const viewportWidth = document.documentElement.clientWidth;
    const clipped: Array<{ name: string; overflowPx: number }> = [];
    const overlaps: string[] = [];
    if (!header) return { clipped, overlaps };

    const name = (el: Element): string =>
      el.getAttribute('aria-label') ||
      el.getAttribute('title') ||
      (el.textContent ?? '').trim().slice(0, 24) ||
      el.tagName.toLowerCase();

    const controls = Array.from(header.querySelectorAll('a, button')).filter(el => {
      const r = el.getBoundingClientRect();
      return r.width > 0 && r.height > 0;
    });

    for (const el of controls) {
      const r = el.getBoundingClientRect();
      if (r.right > viewportWidth + 1) {
        clipped.push({
          name: name(el),
          overflowPx: Math.round((r.right - viewportWidth) * 10) / 10,
        });
      }
    }

    for (let i = 0; i < controls.length; i++) {
      for (let j = i + 1; j < controls.length; j++) {
        // Skip nesting (a button inside a link): only siblings can "cover".
        if (controls[i].contains(controls[j]) || controls[j].contains(controls[i])) continue;
        const a = controls[i].getBoundingClientRect();
        const b = controls[j].getBoundingClientRect();
        if (
          a.left < b.right - 1 &&
          b.left < a.right - 1 &&
          a.top < b.bottom - 1 &&
          b.top < a.bottom - 1
        ) {
          overlaps.push(`${name(controls[i])} ×× ${name(controls[j])}`);
        }
      }
    }
    return { clipped, overlaps };
  });
}

test.describe('dashboard header reachability', () => {
  for (const locale of LOCALES) {
    test(`no control is clipped or covered @ ${locale}`, async ({
      page,
      authenticate,
      mockApi,
    }) => {
      await authenticate({ language: locale });
      await mockApi(ROUTES);
      await page.goto(`/${locale}/dashboard/chat`);
      await page.locator('header').waitFor({ state: 'visible' });
      await waitForStableHeader(page);

      for (const width of WIDTHS) {
        await page.setViewportSize({ width, height: 800 });
        await page.waitForFunction(w => document.documentElement.clientWidth === w, width);
        await waitForStableHeader(page);

        const { clipped, overlaps } = await probeHeader(page);

        expect(
          clipped,
          `${locale} @ ${width}px — controls pushed off-screen: ` +
            clipped.map(c => `${c.name} (+${c.overflowPx}px)`).join(', ')
        ).toEqual([]);
        expect(
          overlaps,
          `${locale} @ ${width}px — controls overlap: ${overlaps.join(' | ')}`
        ).toEqual([]);
      }
    });
  }

  /**
   * Space was reclaimed by shrinking the controls — but only in the narrow band
   * that actually needed it. Above 380 px every header control keeps a 44 px
   * touch target (WCAG 2.5.5 AAA); below it they drop to 36 px, still well past
   * the 24 px AA floor of 2.5.8. Without this guard, the next "let's gain a few
   * pixels" change would silently pay for the room with ergonomics.
   */
  test('header controls keep a 44 px touch target above 380 px', async ({
    page,
    authenticate,
    mockApi,
  }) => {
    await authenticate({ language: 'de' });
    await mockApi(ROUTES);
    await page.setViewportSize({ width: 390, height: 800 });
    await page.goto('/de/dashboard/chat');
    await page.locator('header').waitFor({ state: 'visible' });
    await waitForStableHeader(page);

    const tooSmall = await page.evaluate(() => {
      const header = document.querySelector('header');
      if (!header) return [];
      return Array.from(header.querySelectorAll('button'))
        .map(el => ({
          name: el.getAttribute('aria-label') ?? el.tagName,
          height: Math.round(el.getBoundingClientRect().height),
        }))
        .filter(c => c.height > 0 && c.height < 44);
    });
    expect(
      tooSmall,
      `controls under 44 px at 390 px: ${tooSmall.map(c => `${c.name}=${c.height}px`).join(', ')}`
    ).toEqual([]);
  });

  test('the logout control is always operable at the reflow floor', async ({
    page,
    authenticate,
    mockApi,
  }) => {
    // The most consequential case: a user must always be able to sign out.
    await authenticate({ language: 'de' });
    await mockApi(ROUTES);
    await page.setViewportSize({ width: 320, height: 800 });
    await page.goto('/de/dashboard/chat');

    const logout = page.locator('header button').last();
    await expect(logout).toBeVisible();
    const box = await logout.boundingBox();
    expect(box).not.toBeNull();
    expect(
      box!.x + box!.width,
      'logout right edge must stay inside the viewport'
    ).toBeLessThanOrEqual(321);
  });
});
