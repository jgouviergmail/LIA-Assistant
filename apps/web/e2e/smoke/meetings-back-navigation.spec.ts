/**
 * The way back from the meetings list (owner, 2026-09-10).
 *
 * Six doors lead to those pages and the list had none back — a reader who
 * opened it from the header was stranded unless they typed a URL. The browser's
 * own history is not the answer (it dies on a reload, and after deleting a
 * meeting it points at a page that no longer exists), so the door that was used
 * travels in the URL as a TOKEN of the dashboard's destination table, and a
 * token nobody declared falls back to the chat.
 *
 * Only a real browser proves the two halves meet: the HEADER has to stamp the
 * link, and the LIST has to read the stamp. A unit test can prove either one
 * alone while the pair does nothing.
 */
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

  test('offers the chat as a way out when no door was recorded', async ({
    page,
    authenticate,
    mockApi,
  }) => {
    await authenticate({ language: 'fr' });
    await mockApi(meetingRoutes());

    await page.goto('/fr/dashboard/meetings');
    await waitForHydration(page, TITLE);

    await page.getByRole('button', { name: 'Chat', exact: true }).click();
    await expect(page).toHaveURL(/\/dashboard\/chat$/);
  });

  test('leads back to the screen the header was clicked from', async ({
    page,
    authenticate,
    mockApi,
  }) => {
    await authenticate({ language: 'fr' });
    await mockApi(meetingRoutes());

    // Start on Relations, reach Meetings through the header.
    await page.setViewportSize({ width: 1440, height: 900 });
    await page.goto('/fr/dashboard/relations');
    await page.getByRole('link', { name: 'Réunions' }).click();

    // The stamp is in the URL — that is what makes the way back survive a
    // reload, which is exactly what the browser history does not.
    await expect(page).toHaveURL(/\/dashboard\/meetings\?from=relations/);
    await page.reload();
    await waitForHydration(page, TITLE);
    // Wait for the LIST's terminal state before clicking: a page still
    // settling (config → features → nav → recorder banner) moves the button
    // under the pointer, and Playwright retries into a detached node.
    await expect(page.getByRole('button', { name: 'Relations', exact: true })).toBeVisible({
      timeout: 15000,
    });

    await page.getByRole('button', { name: 'Relations', exact: true }).click();
    await expect(page).toHaveURL(/\/dashboard\/relations$/);
  });

  test('never follows a token that names anything but a screen', async ({
    page,
    authenticate,
    mockApi,
  }) => {
    await authenticate({ language: 'fr' });
    await mockApi(meetingRoutes());

    await page.goto('/fr/dashboard/meetings?from=https%3A%2F%2Fevil.example.com');
    await waitForHydration(page, TITLE);

    await page.getByRole('button', { name: 'Chat', exact: true }).click();
    await expect(page).toHaveURL(/\/dashboard\/chat$/);
  });
});
