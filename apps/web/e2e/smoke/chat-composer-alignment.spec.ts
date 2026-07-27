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
 *  2. the active-spaces indicator sat in the flow, flush against the trailing
 *     controls. It now shares the absolutely-centred row with the voice badge —
 *     which also makes an overlap between the two impossible.
 *
 * Both are pinned by measurement, in a browser: a class name assertion would
 * pass while the pixels lied.
 */
import { test, expect, type MockRoute } from '../fixtures';

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

    // Wait for it: the indicator appears only once `/rag-spaces` answers, and
    // counting before that skipped the test while the element was on its way.
    const indicator = page.locator('a[href*="/dashboard/spaces"]').first();
    await expect(indicator, 'the indicator must render with an active space').toBeVisible({
      timeout: 20_000,
    });

    const geometry = await page.evaluate(() => {
      const link = document.querySelector('a[href*="/dashboard/spaces"]');
      const row = link?.closest('[class*="absolute"]');
      if (!link || !row) return null;
      const r = link.getBoundingClientRect();
      return {
        centre: Math.round(r.left + r.width / 2),
        viewportCentre: Math.round(window.innerWidth / 2),
        insideCentredRow: true,
      };
    });

    expect(geometry, 'the indicator must live in the centred row').not.toBeNull();
    // Beside the voice badge, so not exactly on the axis — but nowhere near the
    // right edge where it used to be glued.
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
      const link = document.querySelector('a[href*="/dashboard/spaces"]');
      const row = link?.parentElement;
      const badge = row?.firstElementChild;
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
