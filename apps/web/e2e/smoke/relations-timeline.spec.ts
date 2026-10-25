/**
 * The relationship timeline (owner request 2026-10-24) — the card's dated
 * records on one line, newest first, on a desktop and on a phone.
 *
 * Unit tests cover the merge, the cursor and the section; the browser proves
 * the journey on the real layout: folded, the section states every row it
 * holds and asks nothing; opened, it reads the first page and places the mail
 * the card already read among the records, the meeting still to come leading;
 * « Older » follows the cursor until the API says nothing is left.
 */
import { test, expect } from '../fixtures';
import { relationTimelinePage, relationsData } from '../fixtures/relations';
import { awaitStyledPage, expectNoOverflow } from './overflow-report';

/** Both doors of the timeline, with or without a cursor. */
const TIMELINE = /\/api\/v1\/relations\/[^/?]+\/timeline(\?.*)?$/;

/** The fixture's fifth record, served behind the first page's cursor. */
const OLDER_PAGE = {
  items: [
    {
      kind: 'memory',
      at: '2026-07-18T08:30:00Z',
      open_loop: null,
      call: null,
      memory: {
        id: 'm1',
        content: 'Aime la randonnée en montagne.',
        created_at: '2026-07-18T08:30:00Z',
      },
      peer_message: null,
      sms: null,
    },
  ],
  next_cursor: null,
  page_size: 4,
};

const DEVICES = [
  { device: 'desktop', viewport: { width: 1280, height: 900 } },
  { device: 'phone', viewport: { width: 375, height: 812 } },
] as const;

for (const { device, viewport } of DEVICES) {
  test.describe(`relations timeline (${device})`, () => {
    test.use({ viewport });

    test('folded it asks nothing; opened it reads newest first, older on demand', async ({
      page,
      authenticate,
      mockApi,
    }) => {
      const asked: string[] = [];
      await authenticate({ language: 'fr' });
      await mockApi([
        ...relationsData,
        {
          // AFTER the fixture's own timeline route (LIFO): this one answers
          // the cursor too, and records what was asked.
          url: TIMELINE,
          method: 'GET',
          handler: route => {
            const url = new URL(route.request().url());
            asked.push(url.search);
            return route.fulfill({
              json: url.searchParams.has('cursor') ? OLDER_PAGE : relationTimelinePage,
            });
          },
        },
      ]);
      await page.goto('/fr/dashboard/relations');
      await awaitStyledPage(page, `relations timeline (${device})`);
      await page
        .getByRole('main')
        .getByRole('button')
        .filter({ hasText: 'Gérard Dupont' })
        .first()
        .click();

      // Folded, the index states every row the timeline holds — the card's
      // five records, the e-mail and the meeting to come — and asked nothing.
      const toggle = page.getByRole('button', { name: /^Chronologie/ });
      await expect(toggle).toHaveAttribute('aria-expanded', 'false', { timeout: 30_000 });
      await expect(toggle).toContainText('7');
      expect(asked).toEqual([]);

      await toggle.click();
      // The ARIA link, not a guess at the markup: the panel the toggle controls.
      const panelId = await toggle.getAttribute('aria-controls');
      const timeline = page.locator(`[id="${panelId}"]`);
      const rows = timeline.getByRole('listitem');
      // The kind leads each row as text (no icon), then when, then the words.
      await expect(rows).toHaveText([
        /^Rendez-vous[\s\S]*Visite du chantier/,
        /^Email[\s\S]*Devis pour la terrasse[\s\S]*chiffrage révisé/,
        /^Message[\s\S]*sera en retard/,
        /^Message[\s\S]*Texte non conservé/,
        /^Appel[\s\S]*Anniversaire surprise[\s\S]*Il est partant/,
        /^Engagement[\s\S]*Rendre la perceuse/,
      ]);
      await expect(timeline.getByRole('heading', { name: 'À venir' })).toBeVisible();
      expect(asked).toEqual(['']);

      await timeline.getByRole('button', { name: 'Plus ancien' }).click();
      await expect(rows).toHaveCount(7);
      await expect(rows.last()).toHaveText(/^Souvenir[\s\S]*Aime la randonnée en montagne\./);
      // The API said nothing is left: the control goes.
      await expect(timeline.getByRole('button', { name: 'Plus ancien' })).toHaveCount(0);
      expect(asked).toEqual(['', '?cursor=e2e-after-the-open-loop']);
      await expectNoOverflow(page, `relations timeline unfolded (${device})`);
    });
  });
}
