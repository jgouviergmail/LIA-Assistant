/**
 * The composer row and the status row, measured (UX polish).
 *
 * Two defects reported from a screenshot, both invisible to every existing
 * test because nothing measured geometry here:
 *
 *  1. the paperclip, the field and the send button were NOT aligned. A
 *     `<textarea>` is an INLINE element, so its baseline added ~6 px under it:
 *     its wrapper grew to 54 px while all three controls stayed 48 px, and the
 *     field floated 6 px above them. `display: block` removes the baseline.
 *  2. the active-spaces indicator sat flush against the trailing controls. It
 *     now rides in the header's centred MIDDLE group beside the voice badge
 *     (v1.26.0: equal-weight flex sides keep that group centred and let it
 *     shift rather than overlap — the former `absolute` centring reserved no
 *     width and overlapped the search). Being siblings makes an overlap
 *     between the two impossible. Targeted by the indicator's own testid, never
 *     a `/dashboard/spaces` link (R01 put one in the nav too).
 *
 * Both are pinned by measurement, in a browser: a class name assertion would
 * pass while the pixels lied.
 */
import { test, expect, waitForHydration, type MockRoute } from '../fixtures';

const ROUTES: MockRoute[] = [
  {
    url: '**/api/v1/conversations/me/messages*',
    json: {
      messages: [],
      conversation_id: null,
      total_count: 0,
      has_more: false,
      next_cursor: null,
    },
  },
  { url: '**/api/v1/conversations/me/totals', json: {} },
  { url: '**/api/v1/agents/health', json: { status: 'healthy', graph_compiled: true } },
  { url: '**/api/v1/agents/runs/active', json: { active: false } },
  { url: '**/api/v1/agents/hitl/pending', json: null },
  { url: '**/api/v1/usage/**', json: {} },
  // Two active spaces, so the indicator renders (it returns null at zero).
  {
    url: '**/api/v1/rag-spaces**',
    json: {
      spaces: [
        { id: 's1', name: 'Docs', is_active: true },
        { id: 's2', name: 'Notes', is_active: true },
      ],
      total: 2,
    },
  },
];

test.describe('composer alignment', () => {
  test('the paperclip, the field and the send button share one baseline', async ({
    page,
    authenticate,
    mockApi,
  }) => {
    await authenticate({ language: 'fr' });
    await mockApi(ROUTES);
    await page.goto('/fr/dashboard/chat');
    const field = page.locator('form textarea').first();
    await expect(field).toBeVisible({ timeout: 30_000 });

    // Polled: the row settles after the thread mounts above it.
    await expect
      .poll(
        async () =>
          page.evaluate(() => {
            const form = document.querySelector('form');
            const textarea = form?.querySelector('textarea');
            // VISIBLE buttons only: the form also holds controls that are
            // hidden by state (stop/send swap, slash menu), and measuring a
            // display:none box compares nothing.
            const buttons = form
              ? Array.from(form.querySelectorAll('button')).filter(
                  b => (b as HTMLElement).offsetParent !== null
                )
              : [];
            if (!form || !textarea || buttons.length < 2) return null;
            const box = (el: Element) => {
              const r = el.getBoundingClientRect();
              return { top: Math.round(r.top), bottom: Math.round(r.bottom) };
            };
            const first = box(buttons[0]);
            const last = box(buttons[buttons.length - 1]);
            const field = box(textarea);
            // Largest disagreement between the three bottom edges.
            return Math.max(
              Math.abs(field.bottom - first.bottom),
              Math.abs(field.bottom - last.bottom),
              Math.abs(first.bottom - last.bottom)
            );
          }),
        { message: 'the three controls must share a bottom edge' }
      )
      // One pixel of rounding is tolerable; six is the defect that was reported.
      .toBeLessThanOrEqual(1);
  });

  test('the active-spaces indicator is centred, not flush right', async ({
    page,
    authenticate,
    mockApi,
  }) => {
    await authenticate({ language: 'fr' });
    await mockApi(ROUTES);
    await page.goto('/fr/dashboard/chat');
    await expect(page.locator('form textarea').first()).toBeVisible({ timeout: 30_000 });

    // The indicator is the header's OWN control (a dropdown trigger since R01),
    // not any `/dashboard/spaces` link — the nav carries one too. Target it by
    // its stable testid so the nav link can never stand in for it. It appears
    // only once `/rag-spaces` answers.
    const indicator = page.getByTestId('active-spaces-indicator');
    await expect(indicator, 'the indicator must render with an active space').toBeVisible({
      timeout: 20_000,
    });

    const geometry = await page.evaluate(() => {
      const el = document.querySelector('[data-testid="active-spaces-indicator"]');
      if (!el) return null;
      const r = el.getBoundingClientRect();
      return {
        centre: Math.round(r.left + r.width / 2),
        viewportCentre: Math.round(window.innerWidth / 2),
      };
    });

    expect(geometry, 'the indicator must be laid out').not.toBeNull();
    // Beside the voice badge in the centred group, so not exactly on the axis —
    // but nowhere near the right edge where it used to be glued.
    expect(Math.abs(geometry!.centre - geometry!.viewportCentre)).toBeLessThan(220);
  });

  test('the indicator never overlaps the voice badge', async ({ page, authenticate, mockApi }) => {
    // They share one flex row, so this is true by construction — pinned so a
    // future move back to absolute positioning is caught.
    await authenticate({ language: 'fr' });
    await mockApi(ROUTES);
    await page.goto('/fr/dashboard/chat');
    await expect(page.locator('form textarea').first()).toBeVisible({ timeout: 30_000 });

    const overlap = await page.evaluate(() => {
      const link = document.querySelector('[data-testid="active-spaces-indicator"]');
      // The voice badge is the sibling right before the indicator in the group.
      const badge = link?.previousElementSibling;
      if (!link || !badge || badge === link) return 0;
      const a = link.getBoundingClientRect();
      const b = badge.getBoundingClientRect();
      const horizontal = Math.min(a.right, b.right) - Math.max(a.left, b.left);
      const vertical = Math.min(a.bottom, b.bottom) - Math.max(a.top, b.top);
      return horizontal > 0 && vertical > 0 ? Math.round(horizontal) : 0;
    });

    expect(overlap, 'the two must not share pixels').toBe(0);
  });
});

test.describe('mobile composer space and touch access', () => {
  test.use({ hasTouch: true });

  for (const width of [320, 375]) {
    test(`at ${width}px: typing keeps the width while the attachment target stays reachable`, async ({
      page,
      authenticate,
      mockApi,
    }, testInfo) => {
      await page.setViewportSize({ width, height: 812 });
      await authenticate({ language: 'fr' });
      await mockApi(ROUTES);
      await page.goto('/fr/dashboard/chat');
      const field = page.locator('form textarea').first();
      const plus = page.getByRole('button', { name: 'Joindre un fichier', exact: true });
      await expect(field).toBeVisible({ timeout: 30_000 });
      await waitForHydration(page);
      // The development overlay is not application chrome. Its floating badge
      // otherwise intercepts the bottom-left touch on a phone-width viewport.
      // Hiding this portal leaves normal hit testing on every app control.
      await page.addStyleTag({ content: 'nextjs-portal { display: none !important; }' });

      await expect
        .poll(async () =>
          field.evaluate(element => {
            const style = getComputedStyle(element);
            return (
              element.clientWidth -
              Number.parseFloat(style.paddingLeft) -
              Number.parseFloat(style.paddingRight)
            );
          })
        )
        // Keep at least 150px of actual typing width on a 320px display,
        // excluding textarea padding and preserving the dashboard gutters.
        // The old separated controls left roughly 106px: a >=40px gain.
        .toBeGreaterThanOrEqual(width - 170);

      const assertControlGeometry = async () => {
        const geometry = await field.evaluate(element => {
          const form = element.closest('form');
          const buttons = Array.from(form?.querySelectorAll('button') ?? []).filter(
            button => button.offsetParent !== null
          );
          const first = buttons[0]?.getBoundingClientRect();
          const last = buttons.at(-1)?.getBoundingClientRect();
          const text = element.getBoundingClientRect();
          if (!first || !last) return null;
          return {
            textWidth:
              element.clientWidth -
              Number.parseFloat(getComputedStyle(element).paddingLeft) -
              Number.parseFloat(getComputedStyle(element).paddingRight),
            targetWidth: first.width,
            targetHeight: first.height,
            sendWidth: last.width,
            sendHeight: last.height,
            leftOverlap: first.right - text.left,
            rightOverlap: text.right - last.left,
            bottomDifference: Math.max(
              Math.abs(first.bottom - text.bottom),
              Math.abs(last.bottom - text.bottom)
            ),
            overflow: document.documentElement.scrollWidth - window.innerWidth,
          };
        });
        expect(geometry).not.toBeNull();
        expect(geometry!.targetWidth).toBeGreaterThanOrEqual(44);
        expect(geometry!.targetHeight).toBeGreaterThanOrEqual(44);
        expect(geometry!.sendWidth).toBeGreaterThanOrEqual(44);
        expect(geometry!.sendHeight).toBeGreaterThanOrEqual(44);
        expect(geometry!.leftOverlap).toBeLessThanOrEqual(1);
        expect(geometry!.rightOverlap).toBeLessThanOrEqual(1);
        expect(geometry!.bottomDifference).toBeLessThanOrEqual(1);
        expect(geometry!.overflow).toBeLessThanOrEqual(1);
        return geometry;
      };
      await assertControlGeometry();

      const initialHeight = (await field.boundingBox())!.height;
      const draft = 'Prépare ma journée.\nRésume mes rendez-vous.\nGarde les points importants.';
      await field.fill(draft);
      await expect(field).toHaveValue(draft);
      await expect
        .poll(async () => (await field.boundingBox())?.height ?? 0)
        .toBeGreaterThan(initialHeight);
      const geometry = await assertControlGeometry();

      // Actual touch activation, with the browser's normal overlap checks.
      await plus.tap();
      const menu = page.getByRole('menu');
      await expect(menu).toBeVisible();
      await expect(menu.getByRole('menuitem', { name: /espace de connaissances/ })).toBeVisible();
      await page.keyboard.press('Escape');
      await expect(menu).toBeHidden();
      await expect(plus).toBeFocused();
      await field.tap();
      await expect(field).toBeFocused();
      await expect(field).toHaveValue(draft);

      await testInfo.attach('composer-geometry', {
        body: JSON.stringify({ viewport: width, ...geometry }),
        contentType: 'application/json',
      });
      if (width === 375) {
        await page.screenshot({ path: testInfo.outputPath('composer-mobile-full.png') });
        await page.screenshot({
          path: testInfo.outputPath('composer-mobile-final.png'),
          clip: { x: 0, y: 512, width: 375, height: 300 },
        });
      }
    });
  }
});
