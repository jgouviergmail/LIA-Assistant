/** Historical contact values and sibling qualifiers reflow without rewriting their HTML. */
import { test, expect, waitForHydration } from '../fixtures';
import { loadedChatRoutes } from '../fixtures/chat';
import { awaitStyledPage, expectNoOverflow, prepareTheme } from './overflow-report';

const address =
  'un.tres.long.prenom.nom-pour-verifier-archive@long-domaine-professionnel.example.test';

function archivedContact(version: number): string {
  const versionAttribute = version === 2 ? ' data-card-version="2"' : '';
  // Stored render_d_row markup before typed_contact_row grouped the value:
  // the icon, link and badge are siblings in both historical surfaces.
  return `<div class="lia-response-wrapper"${versionAttribute}>
    <div class="lia-card lia-contact">
      <div class="lia-card-top"><div class="lia-card-top__info">
        <span class="lia-card-top__title">Contact archivé ${version}</span>
      </div></div>
      <div class="lia-contact__directory"><div class="lia-d-row">
        <span class="material-symbols-outlined" aria-hidden="true">mail</span>
        <a href="mailto:${address}">${address}</a>
        <span class="lia-tbadge lia-tbadge--work">Professionnel</span>
      </div></div>
    </div>
  </div>`
    .replace(/>\s+</g, '><')
    .trim();
}

test.use({ hasTouch: true });

for (const width of [320, 390]) {
  for (const theme of ['light', 'dark'] as const) {
    test(`archived contact values at ${width}px ${theme} with 200% text`, async ({
      page,
      authenticate,
      mockApi,
    }) => {
      await page.setViewportSize({ width, height: 1100 });
      await prepareTheme(page, theme);
      await authenticate({ language: 'fr', theme, response_display_mode: 'html_cards' });
      await mockApi([
        ...loadedChatRoutes(),
        {
          url: '**/api/v1/conversations/me/messages*',
          json: {
            messages: [1, 2].map(version => ({
              id: `00000000-0000-4000-8000-00000000ac0${version}`,
              role: 'assistant',
              content: archivedContact(version),
              created_at: '2026-10-03T09:30:00Z',
              metadata: null,
            })),
            conversation_id: '00000000-0000-4000-8000-00000000ac00',
            total_count: 2,
            has_more: false,
            next_cursor: null,
          },
        },
      ]);
      await page.goto('/dashboard/chat', { waitUntil: 'domcontentloaded' });
      await waitForHydration(page);
      await awaitStyledPage(page, 'archived contact values');
      await page.evaluate(() => {
        document.documentElement.style.setProperty('--lia-text-scale', '2');
      });
      const cards = page.locator('.lia-contact');
      await expect(cards).toHaveCount(2);
      for (const card of await cards.all()) {
        const link = card.getByRole('link', { name: address, exact: true });
        await expect(link).toHaveAttribute('href', `mailto:${address}`);
        await expect(card.getByText('Professionnel', { exact: true })).toBeVisible();
        await link.focus();
        await expect(link).toBeFocused();
        const geometry = await card.locator('.lia-d-row').evaluate(row => {
          const link = row.querySelector('a');
          const badge = row.querySelector('.lia-tbadge');
          const icon = row.querySelector('.material-symbols-outlined');
          if (!link || !badge || !icon) throw new Error('Missing archived contact facts');
          const range = document.createRange();
          range.selectNodeContents(link);
          const fragments = [...range.getClientRects()];
          const first = fragments[0];
          const last = fragments.at(-1);
          if (!first || !last) throw new Error('Archived address has no painted text');
          const bounds = row.getBoundingClientRect();
          const qualifier = badge.getBoundingClientRect();
          return {
            contentWidth: row.scrollWidth,
            rowWidth: row.clientWidth,
            firstLeft: first.left,
            fragmentLefts: fragments.map(fragment => fragment.left),
            widestLine: Math.max(...fragments.map(fragment => fragment.width)),
            textRoom: bounds.right - first.left,
            lastRight: last.right,
            lastBottom: last.bottom,
            badgeLeft: qualifier.left,
            badgeTop: qualifier.top,
            badgeRight: qualifier.right,
            rowRight: bounds.right,
            iconRight: icon.getBoundingClientRect().right,
          };
        });
        expect(geometry.contentWidth).toBeLessThanOrEqual(geometry.rowWidth + 1);
        expect(geometry.widestLine).toBeGreaterThan(geometry.textRoom * 0.8);
        expect(geometry.iconRight).toBeLessThanOrEqual(geometry.firstLeft);
        for (const left of geometry.fragmentLefts)
          expect(Math.abs(left - geometry.firstLeft)).toBeLessThanOrEqual(1);
        expect(geometry.badgeRight).toBeLessThanOrEqual(geometry.rowRight + 1);
        if (geometry.badgeTop >= geometry.lastBottom - 2) {
          expect(geometry.badgeLeft - geometry.firstLeft).toBeGreaterThanOrEqual(3);
          expect(geometry.badgeLeft - geometry.firstLeft).toBeLessThanOrEqual(12);
        } else {
          expect(geometry.badgeLeft - geometry.lastRight).toBeGreaterThanOrEqual(3);
          expect(geometry.badgeLeft - geometry.lastRight).toBeLessThanOrEqual(12);
        }
      }
      await expectNoOverflow(page, `archived contacts ${width} ${theme}`);
    });
  }
}
