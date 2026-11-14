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
import { ANNEX_DISCUSSION_ID, discussionFixture } from '../fixtures/discussions';
import { probeControls, waitForStableControls } from './control-probe';

const WIDTHS = [320, 390, 768, 880, 1024, 1280] as const;
const LOCALES = ['fr', 'de', 'en'] as const;

test.describe('chat header — the destructive action stays named and reachable', () => {
  /**
   * The reset retains its accessible name when its text steps aside to make
   * room. Its target and retained data are covered by the lifecycle journeys.
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
      const reset = page.getByRole('button', { name: 'Réinitialiser' });
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

test.describe('chat header — one row on a phone, in the owner order', () => {
  /**
   * Owner order (2026-11-11): search, hands-free, discussions, context,
   * knowledge spaces — on ONE row, centred in what the reset leaves, the reset
   * itself always against the right edge. The row used to break in two on a
   * phone (the search above, the rest below). The discussion's title is what
   * gives way: with a long one the row still holds, so the annex here carries
   * a title no phone can show whole, and the short « Principale » leaves the
   * slack that proves the centring. Under 19rem of container (a 320 px screen)
   * no row holds six controls: that width keeps the wrapping net, held by the
   * clipped/overlap probes above and by the six-language journey of
   * `chat-secondary-conversations.spec.ts`.
   */
  const SAMPLES = [
    { width: 360, discussion: 'annex' },
    { width: 390, discussion: 'annex' },
    { width: 430, discussion: 'annex' },
    { width: 430, discussion: 'main' },
  ] as const;
  for (const { width, discussion } of SAMPLES) {
    test(`five controls centred, the reset on the right — ${discussion} at ${width} px`, async ({
      page,
      authenticate,
      mockApi,
    }) => {
      const user = await authenticate({ language: 'fr' });
      const fixture = discussionFixture(user.id, {
        annexTitle: 'Préparation du voyage en Italie de cet été',
      });
      await mockApi(fixture.routes);
      await page.setViewportSize({ width, height: 800 });
      await page.goto(
        discussion === 'annex'
          ? `/fr/dashboard/chat?conversation=${ANNEX_DISCUSSION_ID}`
          : '/fr/dashboard/chat'
      );
      await expect(
        page.getByText(discussion === 'annex' ? 'Historique annexe' : 'Historique principal')
      ).toBeVisible();
      await waitForStableControls(page, 'chat-header');

      const controls = [
        page.getByRole('button', { name: "Rechercher dans l'historique", exact: true }),
        page.getByRole('button', { name: 'Activer le mode mains libres', exact: true }),
        page.getByRole('button', {
          name: discussion === 'annex' ? /^Discussions — Préparation du voyage/ : /^Discussions — /,
        }),
        page.getByTestId('context-usage-pill'),
        page.getByTestId('active-spaces-indicator'),
        page.getByRole('button', { name: 'Réinitialiser', exact: true }),
      ];
      const boxes: { x: number; y: number; width: number; height: number }[] = [];
      for (const control of controls) {
        await expect(control).toBeVisible();
        const box = await control.boundingBox();
        expect(box, 'every control must be laid out').not.toBeNull();
        boxes.push(box!);
      }
      const right = (index: number) => boxes[index].x + boxes[index].width;

      // Left to right in the owner order, none covering the next.
      for (let i = 1; i < boxes.length; i++) {
        expect(
          right(i - 1),
          `control ${i - 1} ends before control ${i} starts at ${width}px`
        ).toBeLessThanOrEqual(boxes[i].x + 0.5);
      }
      // ONE row: every control's vertical centre lies within every other's box.
      const centres = boxes.map(box => box.y + box.height / 2);
      for (const box of boxes) {
        for (const centre of centres) {
          expect(centre).toBeGreaterThan(box.y);
          expect(centre).toBeLessThan(box.y + box.height);
        }
      }

      // The reset keeps the row's right edge…
      const row = await page.locator('[data-eyes-anchor-end]').locator('xpath=..').boundingBox();
      expect(row, 'the header row must be laid out').not.toBeNull();
      expect(Math.abs(row!.x + row!.width - right(5)), 'reset against the right edge').toBeLessThan(
        1
      );
      // …and the five others stand centred in what it leaves: as much room
      // before the search as between the spaces and the reset, the row's own
      // gap aside.
      const gap = boxes[1].x - right(0);
      const before = boxes[0].x - row!.x;
      const after = boxes[5].x - right(4) - gap;
      expect(before).toBeGreaterThanOrEqual(-0.5);
      expect(Math.abs(before - after), `centred at ${width}px`).toBeLessThanOrEqual(1);
      if (discussion === 'main' && width >= 430) {
        // A short title leaves real slack: without it the centring above
        // would be the trivial equality of two zeros.
        expect(before, 'the short title leaves room on both sides').toBeGreaterThan(2);
      }
    });
  }
});
