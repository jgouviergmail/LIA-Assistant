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
import { probeControls, waitForStableControls } from './control-probe';

/** Widths that matter: the reflow floor, a common phone, and the tablet/split
 *  band where the nav and the control labels are shown SIMULTANEOUSLY, and
 *  `2xl` (1536), where the nav labels and the token counters appear. */
const WIDTHS = [320, 390, 768, 880, 1024, 1280, 1536] as const;
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

/** Every width, one locale: nothing clipped past the viewport, nothing covered. */
async function assertReachableAtEveryWidth(page: Page, locale: string): Promise<void> {
  await page.goto(`/${locale}/dashboard/chat`);
  await page.locator('header').waitFor({ state: 'visible' });
  await waitForStableControls(page, 'dashboard-header');

  for (const width of WIDTHS) {
    await page.setViewportSize({ width, height: 800 });
    await page.waitForFunction(w => document.documentElement.clientWidth === w, width);
    await waitForStableControls(page, 'dashboard-header');

    const { clipped, overlaps } = await probeControls(page, 'dashboard-header');

    expect(
      clipped,
      `${locale} @ ${width}px — controls pushed off-screen: ` +
        clipped.map(c => `${c.name} (+${c.overflowPx}px)`).join(', ')
    ).toEqual([]);
    expect(overlaps, `${locale} @ ${width}px — controls overlap: ${overlaps.join(' | ')}`).toEqual(
      []
    );
  }
}

/**
 * The widest header an instance can serve: the meetings destination and
 * recorder (ADR-258/259) and the radio's control (ADR-324) all offered. The
 * shell's own config offers none of them, so the test above measures a
 * narrower row than production shows.
 */
const EVERY_CONTROL: MockRoute = {
  url: '**/api/v1/config',
  json: {
    sse: { heartbeat_interval_seconds: 30 },
    rate_limits: { enabled: false, per_minute: 60, burst: 10 },
    i18n: { supported_languages: [...LOCALES], default_language: 'en' },
    features: { workboard_enabled: true, meetings_enabled: true, radio_enabled: true },
    capabilities: { radio: { enabled: true, family: 'media' } },
    api_version: 'v1',
  },
};

test.describe('dashboard header reachability', () => {
  for (const locale of LOCALES) {
    test(`no control is clipped or covered @ ${locale}`, async ({
      page,
      authenticate,
      mockApi,
    }) => {
      await authenticate({ language: locale });
      await mockApi(ROUTES);
      await assertReachableAtEveryWidth(page, locale);
    });

    test(`with every feature control offered, none is clipped or covered @ ${locale}`, async ({
      page,
      authenticate,
      mockApi,
    }) => {
      await authenticate({ language: locale });
      await mockApi([...ROUTES, EVERY_CONTROL]);
      await assertReachableAtEveryWidth(page, locale);
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
    await waitForStableControls(page, 'dashboard-header');

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
