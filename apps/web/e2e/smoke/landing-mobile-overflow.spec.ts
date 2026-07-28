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
import { test, expect } from '../fixtures';
import { awaitStyledPage, expectNoOverflow } from './overflow-report';

/**
 * Language matters: the middleware negotiates Accept-Language on `/`, so a
 * default (en-US) browser context sees the ENGLISH landing — and overflow is
 * string-length-dependent (the original hero defect only manifested with the
 * longer French version pill; the English row fits and masks it). The deep
 * animated/scrolled passes therefore pin French — the product's default
 * locale and the one the bug shipped in — and a dedicated static pass sweeps
 * ALL 6 locales so a long German or Spanish string can never regress unseen.
 */
test.describe('landing page — no horizontal overflow on mobile (fr)', () => {
  test.use({
    viewport: { width: 375, height: 812 },
    contextOptions: { reducedMotion: 'no-preference' },
    locale: 'fr-FR',
  });

  test('stays within 375px through the full hero animation cycle', async ({ page }) => {
    // The mockup timeline is pure setTimeout — the clock drives it through a
    // whole 4-act cycle in milliseconds of real time.
    await page.clock.install();
    await page.goto('/');
    await awaitStyledPage(page, 'animation cycle');

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
    await awaitStyledPage(page, 'scrolled sections');

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

test.describe('landing page — every locale stays within 375px', () => {
  // fr-FR context so the unprefixed `/` negotiates to French; the 5 prefixed
  // paths win over Accept-Language anyway (URL path is the middleware's
  // first priority), so one context covers all six.
  test.use({ viewport: { width: 375, height: 812 }, locale: 'fr-FR' });

  // fr is the unprefixed default; the 5 others live under their prefix.
  const LOCALE_PATHS: Array<[string, string]> = [
    ['fr', '/'],
    ['en', '/en'],
    ['de', '/de'],
    ['es', '/es'],
    ['it', '/it'],
    ['zh', '/zh'],
  ];

  test('static render of all 6 locales has no horizontal overflow', async ({ page }) => {
    for (const [lng, path] of LOCALE_PATHS) {
      await page.goto(path);
      await awaitStyledPage(page, `locale ${lng}`);
      const lang = await page.evaluate(() => document.documentElement.lang);
      expect(lang, `${path} should serve ${lng}`).toBe(lng);
      await expectNoOverflow(page, `locale ${lng} initial render`);
      // Quick sweep: reveal every section (short settle — the static layout
      // is what varies per locale; the animated deep-dive runs in fr above).
      const ids = await page.evaluate(() =>
        Array.from(document.querySelectorAll('section[id]'), s => s.id).filter(Boolean)
      );
      for (const id of ids) {
        await page.evaluate(sectionId => {
          document.getElementById(sectionId)?.scrollIntoView();
        }, id);
        await page.waitForTimeout(250);
      }
      await expectNoOverflow(page, `locale ${lng} after full scroll`);
    }
  });
});

test.describe('landing page — WCAG reflow floor', () => {
  test.use({ viewport: { width: 320, height: 700 }, locale: 'fr-FR' });

  test('renders without horizontal overflow at 320px', async ({ page }) => {
    await page.goto('/');
    await awaitStyledPage(page, '320px floor');
    await expectNoOverflow(page, '320px initial render');
  });
});
