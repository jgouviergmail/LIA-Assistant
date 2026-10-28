/**
 * Landing page mobile horizontal-overflow guard.
 *
 * Flex/grid children must never widen the page past the viewport. The
 * functional constellation deliberately scrolls within its own stage, so
 * its dense labels remain readable while the surrounding page still fits.
 *
 * The guard covers the map's family filter, keyboard detail, journey player
 * and search at 375px and 320px, every revealed section, and all six locales.
 * The rest of the landing keeps its decorative animations enabled; the
 * map journey is also exercised with reduced motion and manual steps.
 *
 * The product demonstration lives on `/demo` (`InteractiveChatMockup`). Its
 * six scenes keep text inside FIXED-height cards, which page bounds alone
 * cannot see (2026-07: a truncated query pill and a no-wrap chip row cut text
 * inside the card while the page itself fitted), so every phase of every scene
 * is also measured against its clipping ancestors at 375px and 320px.
 */
import type { Locator, Page } from '@playwright/test';
import { test, expect, waitForHydration } from '../fixtures';
import { unfoldCatalogs, unfoldLandingDetails } from './landing-catalogs';
import { awaitStyledPage, expectNoOverflow } from './overflow-report';
import fr from '../../locales/fr/translation.json';

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

/** Poll the stable list: WebKit's locator polling can wait on the paused fake RAF. */
async function currentStep(steps: Locator): Promise<string> {
  return steps.evaluate(
    root => root.querySelector('[aria-current="step"]')?.textContent?.trim() ?? ''
  );
}
/**
 * Let the player's own timers carry it to `expected`, in small steps, so no
 * phase is skipped and no duration owned by the player is copied here.
 */
async function advanceTo(page: Page, steps: Locator, expected: string): Promise<void> {
  for (let tick = 0; tick < 40 && (await currentStep(steps)) !== expected; tick++)
    await page.clock.runFor(250);
  await expect.poll(() => currentStep(steps)).toBe(expected);
}

async function exerciseDemoScenes(page: Page, width: number): Promise<void> {
  const demo = fr.landing.product_demo;
  const chooser = page.getByRole('group', { name: demo.choose_scene, exact: true });
  const player = chooser.locator('..');
  const steps = player.getByRole('list', { name: demo.steps, exact: true });
  const scene = player.getByText(demo.illustrative, { exact: true }).locator('..');
  const ids = Object.keys(demo.scenes) as (keyof typeof demo.scenes)[];
  await expect(chooser.getByRole('button')).toHaveCount(ids.length);
  await waitForHydration(page, `[aria-label="${demo.choose_scene}"]`);
  // Selecting the scene the page opened on would not restart it, so the tour
  // ends there and every selection replays a scene from its request.
  const opened = await chooser.getByRole('button', { pressed: true }).innerText();
  const tour = [
    ...ids.filter(id => demo.scenes[id].title !== opened.trim()),
    ...ids.filter(id => demo.scenes[id].title === opened.trim()),
  ];
  expect(demo.scenes[tour[tour.length - 1]].title).toBe(opened.trim());
  await chooser.scrollIntoViewIfNeeded();
  await page.clock.runFor(1500);
  // Pin Date across the RPCs, pause at that instant, then restore simulated
  // time so the idle-retention check continues to advance Date.now().
  const pausedAt = await page.evaluate(() => Date.now());
  await page.clock.setFixedTime(pausedAt);
  await page.clock.pauseAt(pausedAt);
  await page.clock.setSystemTime(pausedAt);

  for (const id of tour) {
    const title = demo.scenes[id].title;
    const choice = chooser.getByRole('button', { name: title, exact: true });
    await choice.click();
    await expect(choice).toHaveAttribute('aria-pressed', 'true');
    for (const [step, phase] of [
      [demo.steps_request, 'request'],
      [demo.steps_context, 'context'],
      [demo.steps_result, 'result'],
    ] as const) {
      await advanceTo(page, steps, step);
      await expectNoOverflow(page, `${width}px ${title}: ${phase}`);
      await expectUnclippedScene(scene, `${width}px ${title}: ${phase}`);
    }
    await expect(scene.getByText(demo.scenes[id].result_title, { exact: true })).toBeVisible();
    // The result remains available for reading, without cycling to another
    // scene or letting a later frame push content out of its card.
    const beforeIdle = await page.evaluate(() => Date.now());
    await page.clock.fastForward(10_000);
    expect(await page.evaluate(() => Date.now())).toBe(beforeIdle + 10_000);
    await expect(choice).toHaveAttribute('aria-pressed', 'true');
    expect(await currentStep(steps)).toBe(demo.steps_result);
    await expectUnclippedScene(scene, `${width}px ${title}: retained result`);
  }
  const difference = player.locator('details');
  await difference.locator('summary').click();
  await expect(difference).toHaveJSProperty('open', true);
  await expectNoOverflow(page, `${width}px demo difference`);
  await expectUnclippedScene(player, `${width}px demo difference`);
}

/** The map remains usable without letting its SVG expand the page. */
async function exerciseFunctionalMap(page: Page, width: number): Promise<void> {
  const overview = page.locator('.landing-constellation');
  const constellation = overview.getByRole('group', {
    name: 'Constellation des briques fonctionnelles',
  });
  const conversation = constellation.getByRole('button', {
    name: 'Conversation — Converser et comprendre',
    exact: true,
  });
  const diagramScroll = overview.locator('.lm-scroll-x');
  await waitForHydration(page, '.landing-constellation');
  await expect(constellation).toBeVisible();
  await expect(overview.getByRole('heading', { name: 'Parcours', exact: true })).toBeVisible();
  await expect(overview.getByRole('heading', { name: 'Familles', exact: true })).toBeVisible();

  // The deliberate local overflow must remain scrollable, never hidden by
  // the hero's clip boundary or propagated to the document itself.
  const bounds = await diagramScroll.evaluate(element => ({
    width: element.clientWidth,
    scrollWidth: element.scrollWidth,
    overflowX: getComputedStyle(element).overflowX,
  }));
  expect(bounds.width).toBeLessThanOrEqual(width);
  expect(bounds.scrollWidth).toBeGreaterThan(bounds.width);
  expect(bounds.overflowX).toBe('auto');
  await diagramScroll.evaluate(element => {
    element.scrollLeft = element.scrollWidth;
  });
  await expect.poll(() => diagramScroll.evaluate(element => element.scrollLeft)).toBeGreaterThan(0);
  await expectNoOverflow(page, `${width}px constellation scrolled`);

  const family = overview.getByRole('button', { name: /^Converser et comprendre\s/ });
  await family.click();
  await expect(family).toHaveAttribute('aria-pressed', 'true');
  await expect(conversation).toHaveClass(/is-on/);
  await expectNoOverflow(page, `${width}px family isolated`);
  await family.click();
  await expect(family).toHaveAttribute('aria-pressed', 'false');

  await conversation.focus();
  await conversation.press('Enter');
  const detail = page.getByRole('dialog', { name: 'Conversation', exact: true });
  await expect(detail).toBeVisible();
  await expect(page).toHaveURL(/#f\.chat$/);
  await expect(detail.getByRole('button', { name: 'Fermer le détail' })).toBeFocused();
  await expectNoOverflow(page, `${width}px brick detail`);
  await page.keyboard.press('Escape');
  await expect(detail).not.toBeVisible();
  await expect(conversation).toBeFocused();

  // Reduced motion starts paused. The same real player controls advance
  // its highlighted step and return to the overview without autoplay.
  await page.emulateMedia({ reducedMotion: 'reduce' });
  const flows = overview.getByRole('list', { name: 'Scénarios', exact: true });
  const journey = flows.getByRole('button', {
    name: 'Une demande devient une action',
    exact: true,
  });
  await journey.click();
  await expect(journey).toHaveAttribute('aria-pressed', 'true');
  await expect(
    overview.getByRole('button', { name: 'Lire le parcours', exact: true })
  ).toBeVisible();
  const steps = overview.locator('.lm-steps').getByRole('button');
  await expect(steps.first()).toHaveAttribute('aria-current', 'step');
  await overview.getByRole('button', { name: 'Étape suivante', exact: true }).click();
  await expect(steps.nth(1)).toHaveAttribute('aria-current', 'step');
  await expect(steps.first()).not.toHaveAttribute('aria-current', 'step');
  await expectNoOverflow(page, `${width}px journey second step`);
  await overview.getByRole('button', { name: 'Quitter le parcours', exact: true }).click();
  await expect(journey).toHaveAttribute('aria-pressed', 'false');
  await expect(steps).toHaveCount(0);

  const search = overview.getByRole('searchbox', { name: 'Chercher une brique', exact: true });
  await search.fill('Conversation');
  await search.press('Enter');
  await expect(detail).toBeVisible();
  await expectNoOverflow(page, `${width}px searched brick detail`);
  await page.keyboard.press('Escape');
  await expect(search).toBeFocused();
  await search.fill('');
  await page.emulateMedia({ reducedMotion: 'no-preference' });
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
    test(`keeps the functional map usable without page overflow at ${width}px`, async ({
      page,
    }) => {
      await page.setViewportSize({ width, height: 812 });
      await page.goto('/');
      await awaitStyledPage(page, `${width}px functional map`);
      await expectNoOverflow(page, `${width}px initial render`);
      await exerciseFunctionalMap(page, width);
    });

    test(`keeps all six /demo scenes readable through every phase at ${width}px`, async ({
      page,
    }) => {
      await page.setViewportSize({ width, height: 812 });
      await page.clock.install();
      await page.goto('/demo');
      await awaitStyledPage(page, `${width}px demo scenes`);
      await expectNoOverflow(page, `${width}px demo initial render`);
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
