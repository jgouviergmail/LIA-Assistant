/**
 * Chat header — controls stay reachable and never overlap.
 *
 * The dashboard header got its guard in S10. The chat's own header row is a
 * different element (a `div` inside the shell, not a `<header>` landmark) and
 * was therefore covered by nothing — while S0 measured a real overlap there:
 * at 320 px in French, with a loaded state, the search toggle sat on top of the
 * RAG-spaces indicator, and the row reached 97.8 % occupancy.
 *
 * As with the dashboard header, document-scroll checks are blind to this:
 * `html { overflow-x: hidden }` clips the row, and the voice badge is
 * absolutely positioned, so it can cover a sibling without producing overflow
 * at all. The only reliable oracle compares the control boxes themselves.
 *
 * The LOADED state is what matters: the context pill, the spaces indicator and
 * the status pill only appear once the conversation has totals, active spaces
 * or a run in flight — precisely the state a real user is in, and precisely the
 * one the nominal fixtures never reach.
 */
import { test, expect, loadedChatRoutes } from '../fixtures';
import { probeControls, waitForStableControls } from './control-probe';

const WIDTHS = [320, 390, 768, 880, 1024, 1280] as const;
const LOCALES = ['fr', 'de', 'en'] as const;

test.describe('chat header — the destructive action stays named and reachable', () => {
  /**
   * Resetting the conversation purges every message, every attachment of the
   * user (AI-generated images included), the token summaries, the LangGraph
   * checkpoints and the tool contexts. Its label steps aside below 640 px to
   * make room — the ACTION must not, and a bare trash icon names nothing.
   */
  for (const width of [320, 640, 1280] as const) {
    test(`named and operable at ${width} px`, async ({ page, authenticate, mockApi }) => {
      await authenticate({ language: 'fr' });
      await mockApi(loadedChatRoutes());
      await page.setViewportSize({ width, height: 800 });
      await page.goto('/fr/dashboard/chat');
      await page.locator('textarea').first().waitFor({ state: 'visible' });
      await waitForStableControls(page, 'chat-header');

      // Located by its accessible name, which is exactly what a screen-reader
      // user gets — not by a class or a position.
      const reset = page.getByRole('button', { name: 'Supprimer' });
      await expect(reset).toBeVisible();
      await expect(reset).toBeEnabled();

      const box = await reset.boundingBox();
      expect(box, 'reset button must be laid out').not.toBeNull();
      expect(box!.x + box!.width, `reset button is cut off at ${width}px`).toBeLessThanOrEqual(
        width + 1
      );

      // Keyboard reachable: focusing it must be possible without a pointer.
      await reset.focus();
      await expect(reset).toBeFocused();
    });
  }
});

test.describe('chat header reachability', () => {
  for (const locale of LOCALES) {
    test(`no control is clipped or covered in a loaded chat @ ${locale}`, async ({
      page,
      authenticate,
      mockApi,
    }) => {
      await authenticate({ language: locale });
      await mockApi(loadedChatRoutes());
      await page.goto(`/${locale}/dashboard/chat`);
      await page.locator('textarea').first().waitFor({ state: 'visible' });
      await waitForStableControls(page, 'chat-header');

      for (const width of WIDTHS) {
        await page.setViewportSize({ width, height: 800 });
        await page.waitForFunction(w => document.documentElement.clientWidth === w, width);
        await waitForStableControls(page, 'chat-header');

        const { clipped, overlaps } = await probeControls(page, 'chat-header');
        expect(
          clipped,
          `${locale} @ ${width}px — chat header controls off-screen: ` +
            clipped.map(c => `${c.name} (+${c.overflowPx}px)`).join(', ')
        ).toEqual([]);
        expect(
          overlaps,
          `${locale} @ ${width}px — chat header controls overlap: ${overlaps.join(' | ')}`
        ).toEqual([]);
      }
    });
  }
});

test.describe('chat header — the centre group in the owner order', () => {
  /**
   * Owner order (2026-10-01): hands-free mode, context usage, knowledge
   * spaces — and every one an icon (plus a count for the spaces), the words
   * moved to the accessible names. The hands-free badge is ALWAYS there: off
   * (the fixtures never enable it) it is the greyed door that turns it on.
   */
  for (const width of [320, 1280] as const) {
    test(`hands-free, context, spaces — left to right at ${width} px`, async ({
      page,
      authenticate,
      mockApi,
    }) => {
      await authenticate({ language: 'fr' });
      await mockApi(loadedChatRoutes());
      await page.setViewportSize({ width, height: 800 });
      await page.goto('/fr/dashboard/chat');
      await page.locator('textarea').first().waitFor({ state: 'visible' });
      await waitForStableControls(page, 'chat-header');

      const handsFree = page.getByRole('button', { name: 'Activer le mode mains libres' });
      const context = page.getByTestId('context-usage-pill');
      const spaces = page.getByTestId('active-spaces-indicator');
      await expect(handsFree).toBeVisible();
      await expect(handsFree).toHaveAttribute('aria-pressed', 'false');
      await expect(context).toBeVisible();
      await expect(spaces).toBeVisible();

      const [a, b, c] = await Promise.all([
        handsFree.boundingBox(),
        context.boundingBox(),
        spaces.boundingBox(),
      ]);
      expect(a && b && c, 'the three controls must be laid out').toBeTruthy();
      expect(a!.x + a!.width).toBeLessThanOrEqual(b!.x);
      expect(b!.x + b!.width).toBeLessThanOrEqual(c!.x);

      // Icons only: no visible word on the badge, a bare count on the spaces.
      await expect(handsFree).toHaveText('');
      await expect(spaces).toHaveText('2');
    });
  }
});
