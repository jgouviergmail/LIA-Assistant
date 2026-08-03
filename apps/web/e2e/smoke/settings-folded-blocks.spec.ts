/**
 * The proactivity and interest panels, folded.
 *
 * Both stack a form, a list of switches and a ten-row history. Shown at once
 * that is a wall on a page where the reader came to change one thing. Each
 * block folds CLOSED — and the histories additionally do not FETCH until
 * opened, which is the difference between "not shown" and "not paid for".
 *
 * Only a browser proves the second half: a `<details>` keeps its content in
 * the DOM, so a hook inside a merely-hidden panel would still run and still
 * issue its request. This spec counts the requests that actually left.
 */
import { test, expect, type MockRoute } from '../fixtures';

const HEARTBEAT_SETTINGS = {
  heartbeat_enabled: true,
  heartbeat_min_per_day: 1,
  heartbeat_max_per_day: 3,
  heartbeat_push_enabled: true,
  heartbeat_notify_start_hour: 8,
  heartbeat_notify_end_hour: 22,
  available_sources: ['calendar'],
  disabled_sources: ['emails'],
  all_sources: ['calendar', 'emails', 'departure'],
  source_dependencies: { departure: ['calendar'] },
};

const ROUTES: MockRoute[] = [
  { url: '**/api/v1/heartbeat/settings', json: HEARTBEAT_SETTINGS },
  {
    url: '**/api/v1/heartbeat/history**',
    json: {
      notifications: [
        {
          id: '00000000-0000-4000-8000-0000000000h1',
          created_at: '2026-08-01T09:30:00Z',
          content: 'Il pleuvra cet après-midi, prends un parapluie.',
          sources_used: ['CURRENT_WEATHER'],
          priority: 'medium',
          user_feedback: null,
        },
      ],
      total: 42,
    },
  },
];

test.describe('folded settings blocks', () => {
  test('the eleven source switches are shut on arrival, and say how many are refused', async ({
    page,
    authenticate,
    mockApi,
  }) => {
    await authenticate();
    await mockApi(ROUTES);
    await page.goto('/en/dashboard/settings?section=heartbeat');

    const summary = page.locator('summary', { hasText: 'Notification topics' });
    await expect(summary).toBeVisible({ timeout: 20_000 });
    // Shut: not one switch on screen.
    await expect(page.getByRole('switch', { name: 'Calendar' })).toHaveCount(0);
    // Yet the decision is still legible — one source refused.
    await expect(summary).toContainText('1');

    await summary.click();
    await expect(page.getByRole('switch', { name: 'Calendar' })).toBeVisible();
  });

  test('the history is not fetched until its block is opened', async ({
    page,
    authenticate,
    mockApi,
  }) => {
    const calls: string[] = [];
    page.on('request', request => {
      if (request.url().includes('/heartbeat/history')) calls.push(request.url());
    });

    await authenticate();
    await mockApi(ROUTES);
    await page.goto('/en/dashboard/settings?section=heartbeat');

    const summary = page.locator('summary', { hasText: 'Recent notifications' }).first();
    await expect(summary).toBeVisible({ timeout: 20_000 });
    // A `<details>` keeps its children in the DOM: merely hiding the list
    // would have left the hook running and this count at 1.
    expect(calls, 'a shut history must cost no request').toHaveLength(0);

    await summary.click();

    await expect(page.getByText('Il pleuvra cet après-midi, prends un parapluie.')).toBeVisible();
    expect(calls.length, 'opening it fetches exactly once').toBe(1);
  });
});
