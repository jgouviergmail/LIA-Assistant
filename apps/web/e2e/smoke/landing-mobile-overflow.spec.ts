/**
 * Landing page mobile horizontal-overflow guard.
 *
 * Flex/grid children must never widen the page past the viewport. Below `lg`
 * the comparison arena stacks its criteria one per card, every fact shown, and
 * its challenger tiles keep their three choices on one line down to a 320px
 * phone.
 *
 * The guard covers the comparison's duels at 375px and 320px, every revealed
 * section, and all six locales. The rest of the landing keeps its decorative
 * animations enabled.
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

/** Read the present list without WebKit's RAF-backed locator-presence polling. */
async function currentStep(steps: Locator): Promise<string> {
  return steps.evaluateAll(roots => {
    if (roots.length !== 1) throw new Error('The demonstration must keep exactly one step list');
    return roots[0].querySelector('[aria-current="step"]')?.textContent?.trim() ?? '';
  });
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
  // The timed scene assertions are complete. Restore RAF before a native
  // disclosure click: WebKit waits for two stable frames before scrolling it.
  await page.clock.resume();
  const difference = player.locator('details');
  await difference.locator('summary').click();
  await expect(difference).toHaveJSProperty('open', true);
  await expectNoOverflow(page, `${width}px demo difference`);
  await expectUnclippedScene(player, `${width}px demo difference`);
}

/** The comparison arena stays readable on a phone: stacked criteria, every fact shown. */
async function exerciseComparison(page: Page, width: number): Promise<void> {
  const words = fr.landing.comparison;
  const caption = (name: string) => words.caption.replace('{{name}}', name);
  const section = page.locator('section#comparison');
  await section.scrollIntoViewIfNeeded();
  await waitForHydration(page, '#comparison [role="group"] button');
  // One structure at every width: below `lg` each criterion stacks in a card.
  const agentic = (rival: string) =>
    section
      .getByRole('list', { name: caption(rival) })
      .getByRole('listitem')
      .filter({ has: page.getByRole('heading', { level: 3, name: words.rows.agentic.label }) });
  let item = agentic('OpenClaw');
  await expect(item.getByText(words.rows.agentic.openclaw.head)).toBeVisible();
  // Every fact and punchline is shown, never folded (owner, 2026-11-15).
  await expect(item.getByText(words.rows.agentic.lia.b1)).toBeVisible();
  await expect(item.getByText(words.rows.agentic.lia.punch)).toBeVisible();
  await expectNoOverflow(page, `${width}px comparison, LIA facing OpenClaw`);

  const challengers = section.getByRole('group', { name: words.view_label });
  const tops = await challengers
    .getByRole('button')
    .evaluateAll(buttons => buttons.map(button => Math.round(button.getBoundingClientRect().top)));
  expect(tops).toHaveLength(3);
  expect(new Set(tops).size, `${width}px: one line of three challenger tiles`).toBe(1);

  const muse = challengers.getByRole('button', { name: 'Muse', exact: true });
  await muse.click();
  await expect(muse).toHaveAttribute('aria-pressed', 'true');
  await expect(
    section.getByRole('group', { name: words.contenders_label }).getByRole('article')
  ).toHaveCount(2);
  item = agentic('Meta Muse');
  await expect(item.getByText(words.rows.agentic.muse.head)).toBeVisible();
  await expect(item.getByText(words.rows.agentic.muse.b1)).toBeVisible();
  await expectNoOverflow(page, `${width}px comparison duel`);
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
    test(`keeps the comparison usable without page overflow at ${width}px`, async ({ page }) => {
      await page.setViewportSize({ width, height: 812 });
      await page.goto('/');
      await awaitStyledPage(page, `${width}px comparison`);
      await expectNoOverflow(page, `${width}px initial render`);
      await exerciseComparison(page, width);
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
