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
 * ("Einstellungen", "Impostazioni") and were the first to break while the row
 * drew them. Since 2026-10-31 the row draws icons alone at every width (owner);
 * the six locales stay, so a label that comes back is measured where it hurts.
 */
import type { Page } from '@playwright/test';
import AxeBuilder from '@axe-core/playwright';

import { test, expect, type MockRoute } from '../fixtures';
import { probeControls, waitForStableControls } from './control-probe';
import { prepareTheme } from './overflow-report';

/** Widths that matter: the reflow floor, a common phone, and the tablet/split
 *  band where the nav and the control labels are shown SIMULTANEOUSLY, and
 *  `2xl` (1536), where the token counters appear (and the nav labels did,
 *  until the row became icons alone). */
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
 * recorder (ADR-258/259), the radio's control (ADR-324), the world, the
 * « Tools » destination (ADR-369) and the « SMS » one (ADR-357 amendment
 * 2026-10-31) all offered — ten destinations. The shell's own config offers
 * none of them, so the test above measures a narrower row than production shows.
 */
const EVERY_CONTROL: MockRoute = {
  url: '**/api/v1/config',
  json: {
    sse: { heartbeat_interval_seconds: 30 },
    rate_limits: { enabled: false, per_minute: 60, burst: 10 },
    i18n: { supported_languages: [...LOCALES], default_language: 'en' },
    features: {
      workboard_enabled: true,
      meetings_enabled: true,
      radio_enabled: true,
      workbench_enabled: true,
      world_enabled: true,
      sms_enabled: true,
    },
    capabilities: {
      radio: { enabled: true, family: 'media' },
      workbench: { enabled: true, family: 'work' },
      world: { enabled: true, family: 'social' },
      sms: { enabled: true, family: 'communication' },
    },
    api_version: 'v1',
  },
};

test.describe('dashboard header reachability', () => {
  test.describe('French phone navigation', () => {
    // The real browser locale governs the first unprefixed document request.
    test.use({ locale: 'fr-FR' });
    for (const theme of ['light', 'dark'] as const) {
      for (const entryPath of ['/dashboard/chat', '/fr/dashboard/chat']) {
        test(`phone LIA menu names and illustrates every destination in ${theme} from ${entryPath}`, async ({
          page,
          authenticate,
          mockApi,
        }) => {
          await page.setViewportSize({ width: 390, height: 900 });
          await prepareTheme(page, theme);
          await authenticate({ language: 'fr', theme });
          await mockApi([...ROUTES, EVERY_CONTROL]);
          await page.goto(entryPath);
          await waitForStableControls(page, 'dashboard-header');
          const trigger = page.locator('header').getByRole('button', { name: 'Menu', exact: true });
          await trigger.click();
          const menu = page.getByRole('menu');
          const destinations = menu.locator('a[role="menuitem"]');
          await expect(destinations).toHaveCount(10);
          for (const destination of await destinations.all()) {
            await expect(destination).toHaveAccessibleName(/\S+/);
            await expect(destination.locator('svg[aria-hidden="true"]')).toBeVisible();
            expect((await destination.boundingBox())?.height).toBeGreaterThanOrEqual(44);
          }
          await expect(menu.locator('[aria-current="page"]')).toHaveAttribute(
            'href',
            '/dashboard/chat'
          );
          const scan = await new AxeBuilder({ page }).include('[role="menu"]').analyze();
          expect(scan.violations).toEqual([]);
          await menu.screenshot({ path: test.info().outputPath(`lia-menu-${theme}.png`) });
          await page.keyboard.press('Escape');
          await expect(menu).not.toBeVisible();
          await expect(trigger).toBeFocused();
        });
      }
    }
  });

  for (const locale of ['fr', 'de']) {
    test(`enlarged text keeps every header control reachable @ ${locale}`, async ({
      page,
      authenticate,
      mockApi,
    }) => {
      await authenticate({ language: locale });
      await mockApi([...ROUTES, EVERY_CONTROL]);
      await page.setViewportSize({ width: 320, height: 900 });
      await page.goto(`/${locale}/dashboard/chat`);
      await page.locator('header').waitFor({ state: 'visible' });
      await page.evaluate(() => {
        document.documentElement.style.fontSize = '20px';
      });
      await waitForStableControls(page, 'dashboard-header');
      const { clipped, overlaps } = await probeControls(page, 'dashboard-header');
      expect(clipped).toEqual([]);
      expect(overlaps).toEqual([]);
      await page
        .locator('header')
        .screenshot({ path: test.info().outputPath('header-enlarged.png') });
    });
  }
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
   * Owner rule (2026-10-31): from `lg`, the header's icons stand at ONE pitch on
   * both sides. The destinations are icons alone at every width — no label even
   * at `2xl` — and the controls take the destinations' slot and gap, where they
   * kept a 44 px box and a 12 px gap that spread the right side half as wide
   * again as the left. Every icon names itself on hover (the destinations used
   * to be the only ones, with five of the controls). The logout is left out of
   * the pitch: the one destructive act of the row stands a little apart.
   */
  test('the header icons stand at one pitch on both sides, each named on hover', async ({
    page,
    authenticate,
    mockApi,
  }) => {
    await authenticate({ language: 'fr' });
    await mockApi([...ROUTES, EVERY_CONTROL]);
    await page.goto('/fr/dashboard/chat');
    await page.locator('header').waitFor({ state: 'visible' });

    for (const width of [1024, 1280, 1536]) {
      await page.setViewportSize({ width, height: 800 });
      await page.waitForFunction(w => document.documentElement.clientWidth === w, width);
      await waitForStableControls(page, 'dashboard-header');

      const row = await page.evaluate(() => {
        const header = document.querySelector('header');
        if (!header) throw new Error('the dashboard header is not drawn');
        const drawn = (el: Element): boolean => {
          const box = el.getBoundingClientRect();
          return box.width > 0 && box.height > 0;
        };
        const links = Array.from(header.querySelectorAll<HTMLElement>('nav a')).filter(drawn);
        const controls = Array.from(header.querySelectorAll<HTMLElement>('button'))
          .filter(el => drawn(el) && !el.closest('nav'))
          .slice(0, -1);
        const pitches = (icons: HTMLElement[]): number[] =>
          icons
            .slice(1)
            .map((el, i) =>
              Math.round(el.getBoundingClientRect().left - icons[i].getBoundingClientRect().left)
            );
        return {
          destinations: links.length,
          labels: links.map(link => link.innerText.trim()).filter(Boolean),
          untitled: [...links, ...controls]
            .filter(el => !el.title)
            .map(el => el.getAttribute('aria-label') ?? el.tagName),
          left: pitches(links),
          right: pitches(controls),
        };
      });

      expect(row.destinations, `${width}px — destinations drawn`).toBe(10);
      expect(row.labels, `${width}px — destinations showing a label`).toEqual([]);
      expect(row.untitled, `${width}px — icons without a tooltip`).toEqual([]);
      expect(
        new Set([...row.left, ...row.right]),
        `${width}px — pitches left ${row.left.join(',')} / right ${row.right.join(',')}`
      ).toEqual(new Set([row.left[0]]));
    }
  });

  /**
   * Space was reclaimed by shrinking the controls — but only in the narrow band
   * that actually needed it. On the touch layout (below `lg`, where the logo's
   * menu carries the destinations) every header control keeps a 44 px target
   * above 380 px (WCAG 2.5.5 AAA); below it they drop to 36 px, still well past
   * the 24 px AA floor of 2.5.8. From `lg` the controls share the destinations'
   * 36 px slot (owner, 2026-10-31 — the test above). Without this guard, the
   * next "let's gain a few pixels" change would silently pay for the room with
   * ergonomics on a phone.
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
