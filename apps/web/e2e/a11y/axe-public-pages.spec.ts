/**
 * Accessibility smoke for the public pages (2026-07): the cosmos landing
 * (`/` — scroll-scrubbed sections, ghost words, planetarium, and both gallery
 * carousels: a hidden tab panel scans as invisible, so each tab needs its own
 * pass), the landing
 * FAQ (`/faq` — icon section headers, chip anchor rail, native <details>
 * accordions, grouped long answers) and the shareable demo page (`/demo` —
 * the hero animation inside the planetarium). Same AC-002 policy as
 * axe-smoke: EVERY critical/serious violation blocks, color-contrast
 * included, light AND dark (the theme is user-toggled — the stored
 * next-themes localStorage key drives it; the cosmos dark-first script only
 * fires when that key is absent, so seeding it pins each pass).
 *
 * All pages are anonymous: no auth harness, the API catch-all (auto fixture)
 * proves no backend dependency beyond the expected /auth/me 401 probe.
 */
import { test, expect } from '../fixtures';
import { scanPage } from './scan';

const THEMES = ['light', 'dark'] as const;

for (const theme of THEMES) {
  test.describe(`public pages (axe WCAG 2.x A/AA, ${theme})`, () => {
    test.beforeEach(async ({ page }) => {
      await page.addInitScript(storedTheme => {
        try {
          window.localStorage.setItem('theme', storedTheme);
        } catch {
          // Storage may be unavailable (privacy mode) — default theme then.
        }
      }, theme);
    });

    test(`cosmos landing scans clean after a full scroll-through (${theme})`, async ({
      page,
    }, testInfo) => {
      await page.goto('/');
      await expect(page.getByRole('heading', { level: 1 })).toBeVisible();

      // Scroll through every section so the scroll-scrubbed tiles reach their
      // revealed state (--sp → 1) — an opacity-0 tile would be scanned as
      // invisible, making the sweep vacuously clean.
      const ids = await page.evaluate(() =>
        Array.from(document.querySelectorAll('section[id]'), s => s.id).filter(Boolean)
      );
      expect(ids.length, 'the landing must expose its section anchors').toBeGreaterThanOrEqual(10);
      for (const id of ids) {
        await page.evaluate(sectionId => {
          document.getElementById(sectionId)?.scrollIntoView();
        }, id);
        await page.waitForTimeout(200);
      }

      const { blocking, summary } = await scanPage(page, testInfo, `/landing-${theme}`);
      expect(blocking, `axe violations on / (${theme}):\n${summary}`).toHaveLength(0);

      // Second pass on the other gallery tab. A hidden panel is scanned as
      // invisible, so the arrival tab (the deck) is all the pass above covers —
      // and the captures carousel carries one control the deck does not (the
      // full-screen view). Selected by position, not by label: the landing is
      // served in the browser's negotiated locale.
      const capturesTab = page.locator('#gallery [role="tab"]').first();
      await capturesTab.click();
      await expect(capturesTab).toHaveAttribute('aria-selected', 'true');
      const captures = await scanPage(page, testInfo, `/landing-captures-${theme}`);
      expect(
        captures.blocking,
        `axe violations on the / captures tab (${theme}):\n${captures.summary}`
      ).toHaveLength(0);
    });

    test(`FAQ page scans clean with a long grouped answer open (${theme})`, async ({
      page,
    }, testInfo) => {
      await page.goto('/faq');
      await expect(page.getByRole('heading', { level: 1 })).toBeVisible();

      // Open one question card AND one grouped sub-accordion so the scan
      // covers the answer typography (prose links) and the nested summaries.
      await page.evaluate(() => {
        const cards = Array.from(document.querySelectorAll('details'));
        for (const card of cards) {
          if (card.querySelector('details')) {
            card.open = true;
            (card.querySelector('details') as HTMLDetailsElement).open = true;
            return;
          }
        }
        // Fallback: open the first card (grouped answer absent in this locale).
        if (cards[0]) cards[0].open = true;
      });

      const { blocking, summary } = await scanPage(page, testInfo, `/faq-${theme}`);
      expect(blocking, `axe violations on /faq (${theme}):\n${summary}`).toHaveLength(0);
    });

    test(`demo page scans clean (${theme})`, async ({ page }, testInfo) => {
      await page.goto('/demo');
      // The animation is one labelled role="img" inside main (scoped: the
      // Next dev-tools overlay also exposes an svg image on dev servers).
      await expect(page.locator('main [role="img"]')).toBeVisible();

      const { blocking, summary } = await scanPage(page, testInfo, `/demo-${theme}`);
      expect(blocking, `axe violations on /demo (${theme}):\n${summary}`).toHaveLength(0);
    });

    test(`more page scans clean, animating and paused (${theme})`, async ({ page }, testInfo) => {
      await page.goto('/more');
      await expect(page.getByRole('heading', { level: 1 })).toBeVisible();

      // Reveal every section so the FadeInOnScroll content is visible (an
      // opacity-0 card would be scanned as invisible — vacuously clean).
      const ids = await page.evaluate(() =>
        Array.from(document.querySelectorAll('section[id^="more-"]'), s => s.id).filter(Boolean)
      );
      for (const id of ids) {
        await page.evaluate(sectionId => {
          document.getElementById(sectionId)?.scrollIntoView();
        }, id);
        await page.waitForTimeout(200);
      }

      // Pass 1 — scenes running (contrast of every animated frame class mix
      // is token-driven; the scan samples whatever frame is current).
      const animated = await scanPage(page, testInfo, `/more-animating-${theme}`);
      expect(
        animated.blocking,
        `axe on /more animating (${theme}):\n${animated.summary}`
      ).toHaveLength(0);

      // Pass 2 — the WCAG 2.2.2 pause mechanism itself, then the frozen page.
      const toggle = page.getByTestId('more-pause-toggle');
      await expect(toggle).toHaveAttribute('aria-pressed', 'false');
      await toggle.click();
      await expect(toggle).toHaveAttribute('aria-pressed', 'true');

      const paused = await scanPage(page, testInfo, `/more-paused-${theme}`);
      expect(paused.blocking, `axe on /more paused (${theme}):\n${paused.summary}`).toHaveLength(0);
    });
  });
}
