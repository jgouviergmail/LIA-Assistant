/**
 * Accessibility smoke for the redesigned public pages (2026-07): the landing
 * FAQ (`/faq` — icon section headers, chip anchor rail, native <details>
 * accordions, grouped long answers) and the shareable demo page (`/demo` —
 * the hero animation standalone). Same AC-002 policy as axe-smoke: EVERY
 * critical/serious violation blocks, color-contrast included, light AND dark
 * (the theme is user-toggled — `defaultTheme="light"` means emulating the
 * OS scheme does nothing; the next-themes localStorage key drives it).
 *
 * Both pages are anonymous: no auth harness, the API catch-all (auto fixture)
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
