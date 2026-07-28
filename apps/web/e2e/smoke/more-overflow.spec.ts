/**
 * /more page mobile horizontal-overflow guard.
 *
 * Same invariant and helper as the landing guard (overflow-report.ts), with
 * the /more twist: 26 looping scenes driven by setTimeout. The hero lesson
 * (a layout that oscillates only DURING an animation frame) applies — so the
 * 375px pass drives the Playwright clock through full scene cycles per
 * section, asserting at every beat, with animations deliberately ENABLED.
 * A final static pass runs at 320px (WCAG 1.4.10 reflow floor), and a
 * 6-locale static sweep catches long-string regressions (card copy is
 * locale-authored, and German/Spanish run long).
 */

import { test, expect } from '../fixtures';
import { awaitStyledPage, expectNoOverflow } from './overflow-report';

async function revealSections(page: import('@playwright/test').Page): Promise<string[]> {
  const ids = await page.evaluate(() =>
    Array.from(document.querySelectorAll('section[id^="more-"]'), s => s.id).filter(Boolean)
  );
  expect(ids.length).toBeGreaterThanOrEqual(7); // 6 moments + craft band
  return ids;
}

test.describe('/more — no horizontal overflow on mobile (fr), animations running', () => {
  test.use({
    viewport: { width: 375, height: 812 },
    contextOptions: { reducedMotion: 'no-preference' },
    locale: 'fr-FR',
  });

  test('stays within 375px through the scene cycles of every section', async ({ page }) => {
    await page.clock.install();
    await page.goto('/more');
    await awaitStyledPage(page, '/more animation pass');

    await expectNoOverflow(page, 'initial render');

    const ids = await revealSections(page);
    for (const id of ids) {
      await page.evaluate(sectionId => {
        document.getElementById(sectionId)?.scrollIntoView();
      }, id);
      // Let the in-view observers fire, then drive the visible scenes
      // through a full cycle plus its rest (~6s) in 2s beats.
      await page.waitForTimeout(300);
      for (let beat = 1; beat <= 3; beat++) {
        await page.clock.runFor(2_000);
        await expectNoOverflow(page, `section #${id}, beat ${beat}`);
      }
    }
  });
});

test.describe('/more — every locale stays within 375px', () => {
  test.use({ viewport: { width: 375, height: 812 }, locale: 'fr-FR' });

  // fr is the unprefixed default; the 5 others live under their prefix.
  const LOCALE_PATHS: Array<[string, string]> = [
    ['fr', '/more'],
    ['en', '/en/more'],
    ['de', '/de/more'],
    ['es', '/es/more'],
    ['it', '/it/more'],
    ['zh', '/zh/more'],
  ];

  test('static render of all 6 locales has no horizontal overflow', async ({ page }) => {
    for (const [lng, path] of LOCALE_PATHS) {
      await page.goto(path);
      await awaitStyledPage(page, `/more locale ${lng}`);
      const lang = await page.evaluate(() => document.documentElement.lang);
      expect(lang, `${path} should serve ${lng}`).toBe(lng);
      await expectNoOverflow(page, `/more ${lng} initial render`);
      const ids = await revealSections(page);
      for (const id of ids) {
        await page.evaluate(sectionId => {
          document.getElementById(sectionId)?.scrollIntoView();
        }, id);
        await page.waitForTimeout(250);
      }
      await expectNoOverflow(page, `/more ${lng} after full scroll`);
    }
  });
});

test.describe('/more — WCAG reflow floor', () => {
  test.use({ viewport: { width: 320, height: 700 }, locale: 'fr-FR' });

  test('renders without horizontal overflow at 320px', async ({ page }) => {
    await page.goto('/more');
    await awaitStyledPage(page, '/more 320px floor');
    await expectNoOverflow(page, '/more 320px initial render');
    const ids = await revealSections(page);
    for (const id of ids) {
      await page.evaluate(sectionId => {
        document.getElementById(sectionId)?.scrollIntoView();
      }, id);
      await page.waitForTimeout(250);
    }
    await expectNoOverflow(page, '/more 320px after full scroll');
  });
});
