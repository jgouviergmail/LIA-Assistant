/** Detail returns retain the list's query and origin; the list itself has no previous-page link. */
import { test, expect, waitForHydration, type MockRoute } from '../fixtures';
import { pagedMeetingTimeline, meetingTimelineRoutes } from '../fixtures/meeting-timeline';
import { meetingDetail } from '../../src/__tests__/fixtures/meeting-detail';

/** A node the meetings list really renders once hydrated. */
const TITLE = 'h1';

function meetingRoutes(): MockRoute[] {
  return [
    {
      url: '**/api/v1/config',
      json: {
        sse: { heartbeat_interval_seconds: 30 },
        rate_limits: { enabled: false, per_minute: 60, burst: 10 },
        i18n: {
          supported_languages: ['en', 'fr', 'de', 'es', 'it', 'zh'],
          default_language: 'fr',
        },
        // The destination exists only where the instance offers the feature.
        features: { meetings_enabled: true, workboard_enabled: true },
        api_version: 'v1',
      },
    },
    // The REAL contract (`MeetingListResponse`): `items`, not `meetings`.
    // A wrong shape crashes the page into its error boundary, where a
    // loose `getByRole('button', { name: /Chat/i })` still matches the
    // companion's « Ouvrir le chat avec LIA » — a test that passes for the
    // wrong reason.
    { url: '**/api/v1/meetings**', json: { items: [], total: 0, limit: 20, offset: 0 } },
    {
      url: '**/api/v1/meeting-templates**',
      json: { items: [], total: 0, limit: 50, offset: 0 },
    },
  ];
}

test.describe('the meetings list', () => {
  for (const width of [1280, 320]) {
    test(`searches beyond the first page and returns from detail at ${width}px`, async ({
      page,
      authenticate,
      mockApi,
    }) => {
      await page.setViewportSize({ width, height: 900 });
      const errors: string[] = [];
      page.on('pageerror', error => errors.push(error.message));
      const owner = await authenticate({ language: 'fr' });
      const rows = pagedMeetingTimeline();
      const target = { ...rows[22], title: 'Budget café international' };
      rows[22] = target;
      await mockApi([
        ...meetingRoutes(),
        ...meetingTimelineRoutes(owner, rows),
        { url: '**/api/v1/notifications/broadcasts/unread', json: { broadcasts: [] } },
        {
          url: '**/api/v1/meetings?*',
          handler: async route => {
            const params = new URL(route.request().url()).searchParams;
            const q = params.get('q');
            const offset = Number(params.get('offset'));
            const selected = q === 'cafe' ? [target] : rows;
            await route.fulfill({
              json: {
                items: selected.slice(offset, offset + 20),
                total: selected.length,
                limit: 20,
                offset,
              },
            });
          },
        },
        {
          url: `**/api/v1/meetings/${target.id}`,
          json: meetingDetail({
            id: target.id,
            report: { title: target.title, participants: [], sections: [] },
          }),
        },
      ]);
      await page.goto('/fr/dashboard/meetings?from=chat');
      await waitForHydration(page, TITLE);
      const search = page.getByRole('searchbox', { name: 'Rechercher dans les comptes rendus…' });
      await expect(search).toBeVisible();
      await expect(page.getByRole('link', { name: target.title, exact: true })).toHaveCount(0);
      await search.fill('cafe');
      const result = page.getByRole('link', { name: target.title, exact: true });
      await expect(result).toBeVisible();
      await expect(search).toBeFocused();
      await result.click();
      await expect(page).toHaveURL(new RegExp(`/meetings/${target.id}\\?q=cafe&from=chat$`));
      await page.getByRole('button', { name: 'Retour aux réunions', exact: true }).click();
      await expect(page).toHaveURL(/\/meetings\?q=cafe&from=chat$/);
      await expect(search).toHaveValue('cafe');
      await expect(result).toBeVisible();
      expect(
        await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)
      ).toBe(true);
      expect(errors).toEqual([]);
    });
  }

  for (const origin of ['', 'relations', 'https://evil.example.com']) {
    test(
      'has no previous-page link for origin ' + origin,
      async ({ page, authenticate, mockApi }) => {
        await authenticate({ language: 'fr' });
        await mockApi(meetingRoutes());
        await page.goto('/fr/dashboard/meetings?from=' + encodeURIComponent(origin));
        await waitForHydration(page, TITLE);
        const main = page.getByRole('main');
        await expect(main.getByRole('heading', { name: 'Réunions', exact: true })).toBeVisible();
        await expect(main.getByRole('button', { name: /^(Chat|Relations)$/ })).toHaveCount(0);
        await expect(main.getByRole('checkbox')).toHaveCount(0);
      }
    );
  }
});
