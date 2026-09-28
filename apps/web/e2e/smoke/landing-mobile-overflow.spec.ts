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
 * This spec therefore asserts the invariant in three ways:
 *  1. statically after load,
 *  2. across all six selected demo scenes and their three phases, at both
 *     375px and 320px (the Playwright clock drives the reveal timers),
 *  3. after scrolling through every section (chapter vignettes stage on
 *     intersection).
 * A final static pass runs at 320px (WCAG 1.4.10 reflow floor).
 *
 * Animations are deliberately ENABLED (reducedMotion: no-preference overrides
 * the config default): the oscillation only exists with the timeline running.
 */
import type { Locator, Page } from '@playwright/test';
import { test, expect, waitForHydration } from '../fixtures';
import { unfoldCatalogs, unfoldLandingDetails } from './landing-catalogs';
import { awaitStyledPage, expectNoOverflow } from './overflow-report';

const SCENES = ['Décider', 'Écouter', 'Anticiper', 'Déléguer', 'Approfondir', 'Se coordonner'];

/**
 * Horizontal page bounds alone miss text cut INSIDE a fixed-height card.
 * Measure every visible text range against its clipping ancestors. Scrollable
 * ancestors remain reachable; hidden/clip ancestors must contain the text.
 */
async function expectUnclippedScene(scene: Locator, label: string): Promise<void> {
  const clipped = await scene.evaluate(root => {
    const failures: Array<{ text: string; axis: string; container: string }> = [];
    const walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT);
    let textNode: Node | null;
    while ((textNode = walker.nextNode())) {
      if (!textNode.textContent?.trim()) continue;
      const element = textNode.parentElement;
      if (!element || getComputedStyle(element).visibility === 'hidden') continue;
      const range = document.createRange();
      range.selectNodeContents(textNode);
      for (const rect of range.getClientRects()) {
        if (!rect.width || !rect.height) continue;
        for (
          let ancestor: HTMLElement | null = element;
          ancestor;
          ancestor = ancestor.parentElement
        ) {
          const style = getComputedStyle(ancestor);
          const bounds = ancestor.getBoundingClientRect();
          const clipsX = ['hidden', 'clip'].includes(style.overflowX);
          const clipsY = ['hidden', 'clip'].includes(style.overflowY);
          const x = clipsX && (rect.left < bounds.left - 1 || rect.right > bounds.right + 1);
          const y = clipsY && (rect.top < bounds.top - 1 || rect.bottom > bounds.bottom + 1);
          if (x || y) {
            failures.push({
              text: textNode.textContent.trim().slice(0, 100),
              axis: x ? 'horizontal' : 'vertical',
              container: ancestor.className,
            });
            break;
          }
        }
      }
    }
    return failures;
  });
  expect(clipped, `${label}: text clipped inside its illustration`).toEqual([]);
}

async function exerciseDemoScenes(page: Page, width: number): Promise<void> {
  const chooser = page.getByRole('group', { name: 'Choisir une situation' });
  const player = chooser.locator('..');
  const steps = player.getByRole('list', { name: 'Les étapes de la démonstration' });
  const scene = player
    .getByText('Scénario illustratif · personnes, données et résultats fictifs.', { exact: true })
    .locator('..');
  await expect(chooser.getByRole('button')).toHaveCount(SCENES.length);
  await waitForHydration(page, '[aria-label="Choisir une situation"]');
  await chooser.scrollIntoViewIfNeeded();
  await page.clock.runFor(1500);
  // Freeze after hydration and entrance motion. Each replay below starts a
  // fresh timer, so layout checks cannot race the next reveal under CPU load.
  await page.clock.pauseAt(await page.evaluate(() => Date.now() + 100));

  for (const title of SCENES) {
    const choice = chooser.getByRole('button', { name: title, exact: true });
    await choice.click();
    await expect(choice).toHaveAttribute('aria-pressed', 'true');
    await player.getByRole('button', { name: 'Rejouer la démonstration' }).click();
    await expect(steps.locator('[aria-current="step"]')).toHaveText('Ta demande');
    await expectNoOverflow(page, `${width}px ${title}: request`);
    await expectUnclippedScene(scene, `${width}px ${title}: request`);

    await page.clock.runFor(1700);
    await expect(steps.locator('[aria-current="step"]')).toHaveText('Le contexte');
    await expectNoOverflow(page, `${width}px ${title}: context`);
    await expectUnclippedScene(scene, `${width}px ${title}: context`);

    await page.clock.runFor(2400);
    await expect(steps.locator('[aria-current="step"]')).toHaveText('Le résultat');
    await expectNoOverflow(page, `${width}px ${title}: result`);
    await expectUnclippedScene(scene, `${width}px ${title}: result`);
    await expect(scene.getByText(title, { exact: true })).toBeVisible();
    // The result remains available for reading, without cycling to another
    // scenario or letting a later animation frame push content off-screen.
    await page.clock.runFor(10_000);
    await expect(choice).toHaveAttribute('aria-pressed', 'true');
    await expect(steps.locator('[aria-current="step"]')).toHaveText('Le résultat');
    await expectUnclippedScene(scene, `${width}px ${title}: retained result`);
  }
}

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

  for (const width of [375, 320]) {
    test(`keeps all six demo scenes readable through every phase at ${width}px`, async ({
      page,
    }) => {
      await page.setViewportSize({ width, height: 812 });
      await page.clock.install();
      await page.goto('/');
      await awaitStyledPage(page, `${width}px animated scenes`);
      await expectNoOverflow(page, `${width}px initial render`);
      await exerciseDemoScenes(page, width);
    });
  }

  test('stays within 375px across all scrolled sections', async ({ page }) => {
    await page.goto('/');
    await awaitStyledPage(page, 'scrolled sections');

    const sectionIds = await page.evaluate(() =>
      Array.from(document.querySelectorAll('section[id], div#features section'), s => s.id).filter(
        Boolean
      )
    );
    expect(sectionIds.length).toBeGreaterThanOrEqual(10);
    // Folded on arrival: a collapsed catalog has no width to overflow with.
    expect(await unfoldCatalogs(page)).toBeGreaterThan(0);
    expect(await unfoldLandingDetails(page)).toBeGreaterThan(0);

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
      await unfoldCatalogs(page);
      await unfoldLandingDetails(page);
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
