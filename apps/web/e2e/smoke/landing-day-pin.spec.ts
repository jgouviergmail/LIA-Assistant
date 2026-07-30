/**
 * Cosmos landing — the pinned "day" scene must actually pin.
 *
 * ADR-171 doctrine: `position: sticky` silently dies when any ancestor
 * becomes a scrollport, and nothing but a real scroll can prove it works. A
 * static screenshot of the day section looks identical whether the stage
 * sticks or scrolls away with the document — so this spec measures the
 * geometry DURING the traversal:
 *
 *  1. mid-pin, the sticky stage hugs the viewport top (not carried away);
 *  2. the `--p` progress written by PinnedScene actually advances between two
 *     scroll depths (the scrub is live, not stuck at 0 or 1);
 *  3. past the pin, the stage leaves with its wrapper (un-pins at the pixel).
 *
 * Desktop-only on purpose: below the 880px breakpoint (and under
 * prefers-reduced-motion) CosmosDay renders the static vertical timeline —
 * covered by unit tests.
 */
import { test, expect } from '../fixtures';
import { awaitStyledPage } from './overflow-report';

test.describe('cosmos landing — pinned day scene', () => {
  test.use({
    viewport: { width: 1280, height: 900 },
    contextOptions: { reducedMotion: 'no-preference' },
    locale: 'fr-FR',
  });

  test('the day stage pins during scroll and its progress advances', async ({ page }) => {
    await page.goto('/');
    await awaitStyledPage(page, 'cosmos landing');

    const pin = page.locator('.cosmos-pin');
    await expect(pin, 'the pinned scene must exist on desktop').toHaveCount(1);

    // Scroll helper: place the pin wrapper at a given fraction of its own
    // traversal (0 = pin starts, 1 = pin ends), then let two frames settle so
    // the rAF scroll loop writes --p before we measure.
    const measureAt = async (fraction: number) =>
      page.evaluate(async f => {
        const el = document.querySelector<HTMLElement>('.cosmos-pin');
        const stage = document.querySelector<HTMLElement>('.cosmos-pin-stage');
        if (!el || !stage) return null;
        const total = el.offsetHeight - window.innerHeight;
        const start = el.getBoundingClientRect().top + window.scrollY;
        // 'instant' bypasses the landing's global `scroll-behavior: smooth` —
        // a smooth scroll would still be animating when we measure.
        window.scrollTo({ top: Math.round(start + total * f), behavior: 'instant' });
        await new Promise(r => requestAnimationFrame(() => requestAnimationFrame(r)));
        return {
          stageTop: Math.round(stage.getBoundingClientRect().top),
          p: parseFloat(el.style.getPropertyValue('--p') || 'NaN'),
          litCount: document.querySelectorAll('.cosmos-pin .lit').length,
        };
      }, fraction);

    const early = await measureAt(0.25);
    const late = await measureAt(0.75);
    expect(early, 'pin geometry must be measurable').not.toBeNull();
    expect(late).not.toBeNull();

    // 1. Stuck to the viewport top while the document scrolls underneath.
    expect(early!.stageTop, `stage drifted mid-pin (top=${early!.stageTop})`).toBeLessThanOrEqual(2);
    expect(early!.stageTop).toBeGreaterThanOrEqual(-2);
    expect(late!.stageTop, `stage drifted late-pin (top=${late!.stageTop})`).toBeLessThanOrEqual(2);

    // 2. The scrub is alive: progress advances with the scroll and lights
    //    more steps as the day unfolds.
    expect(early!.p).toBeGreaterThan(0.1);
    expect(late!.p, `--p must advance (${early!.p} → ${late!.p})`).toBeGreaterThan(early!.p + 0.3);
    expect(late!.litCount).toBeGreaterThanOrEqual(early!.litCount);

    // 3. Past the pin the stage leaves the viewport top with its wrapper.
    const past = await page.evaluate(async () => {
      const el = document.querySelector<HTMLElement>('.cosmos-pin');
      if (!el) return null;
      const total = el.offsetHeight - window.innerHeight;
      const start = el.getBoundingClientRect().top + window.scrollY;
      window.scrollTo({ top: Math.round(start + total + 600), behavior: 'instant' });
      await new Promise(r => requestAnimationFrame(() => requestAnimationFrame(r)));
      const stage = document.querySelector<HTMLElement>('.cosmos-pin-stage');
      return stage ? Math.round(stage.getBoundingClientRect().top) : null;
    });
    expect(past, 'stage must un-pin once its scroll room is spent').not.toBeNull();
    expect(past!).toBeLessThan(-100);
  });
});
