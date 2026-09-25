/**
 * What an administrator sent, read back under the form (ADR-312).
 *
 * Hermetic: the history pages are mocked and every ask is recorded. Three
 * claims only a laid-out page proves:
 *
 * 1. **Each row says who it went to and when it expires** — « All active
 *    users », or the named accounts with the exact count beyond them; the
 *    chosen delay beside the expiry.
 * 2. **The paging asks the API for the next page** (limit and offset), and the
 *    exact total is what the pagination states — never the length of a page.
 * 3. **At 320 px nothing reaches past the screen.**
 */
import { test, expect, waitForHydration, type MockRoute } from '../fixtures';
import { scanPage } from '../a11y/scan';

function item(index: number, overrides: Record<string, unknown> = {}) {
  return {
    id: `00000000-0000-4000-8000-${String(index).padStart(12, '0')}`,
    message: `Maintenance window number ${index}`,
    sent_at: '2026-09-24T08:00:00Z',
    sender_name: 'Admin',
    audience: 'all',
    recipients: [],
    recipients_total: 0,
    reached_count: 18,
    expires_at: '2026-10-01T08:00:00Z',
    expires_in_days: 7,
    is_expired: false,
    fcm_sent: 12,
    fcm_failed: 0,
    read_count: 5,
    ...overrides,
  };
}

function routes(asked: string[]): MockRoute[] {
  return [
    {
      url: /\/api\/v1\/notifications\/admin\/broadcasts\?/,
      handler: async route => {
        const params = new URL(route.request().url()).searchParams;
        asked.push(`limit=${params.get('limit')}&offset=${params.get('offset')}`);
        const offset = Number(params.get('offset') ?? 0);
        const first = [
          item(1, {
            audience: 'selected',
            recipients: [
              { id: 'u1', full_name: 'Claire Lefèvre', email: 'claire@example.org' },
              { id: 'u2', full_name: 'Gérard Dupont', email: 'gerard@example.org' },
            ],
            recipients_total: 5,
            reached_count: 5,
          }),
          ...Array.from({ length: 9 }, (_, i) => item(i + 2)),
        ];
        await route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify({ items: offset === 0 ? first : [item(11)], total: 11 }),
        });
      },
    },
  ];
}

test.describe('the sent-broadcasts history', () => {
  test('each row states its audience and its expiry', async ({ page, authenticate, mockApi }) => {
    await authenticate({ language: 'en', is_superuser: true });
    await mockApi(routes([]));

    await page.goto('/en/dashboard/settings?section=admin-broadcast');
    await waitForHydration(page, 'textarea');
    await expect(page.getByText('Maintenance window number 1', { exact: true })).toBeVisible();

    // The names are joined the reader's way (Intl.ListFormat), the rest counted.
    await expect(page.getByText('Claire Lefèvre and Gérard Dupont +3')).toBeVisible();
    await expect(page.getByText('All active users').first()).toBeVisible();
    await expect(page.getByText(/7-day delay/).first()).toBeVisible();
  });

  test('the next page is asked of the API, and the total is the exact one', async ({
    page,
    authenticate,
    mockApi,
  }) => {
    await authenticate({ language: 'en', is_superuser: true });
    const asked: string[] = [];
    await mockApi(routes(asked));

    await page.goto('/en/dashboard/settings?section=admin-broadcast');
    await waitForHydration(page, 'textarea');
    await expect(page.getByText('Maintenance window number 1', { exact: true })).toBeVisible();
    await expect.poll(() => asked).toEqual(['limit=10&offset=0']);

    await page.getByRole('button', { name: /next/i }).click();
    await expect(page.getByText('Maintenance window number 11')).toBeVisible();
    expect(asked).toContain('limit=10&offset=10');
  });

  test('at 320 px nothing reaches past the screen', async ({ page, authenticate, mockApi }) => {
    await page.setViewportSize({ width: 320, height: 640 });
    await authenticate({ language: 'en', is_superuser: true });
    await mockApi(routes([]));

    await page.goto('/en/dashboard/settings?section=admin-broadcast');
    await waitForHydration(page, 'textarea');
    await expect(page.getByText('Maintenance window number 1', { exact: true })).toBeVisible();

    const scrolls = await page.evaluate(
      () => document.documentElement.scrollWidth > document.documentElement.clientWidth
    );
    expect(scrolls).toBe(false);
  });

  test('the history scans clean (axe WCAG A/AA)', async ({
    page,
    authenticate,
    mockApi,
  }, testInfo) => {
    await authenticate({ language: 'en', is_superuser: true });
    await mockApi(routes([]));

    await page.goto('/en/dashboard/settings?section=admin-broadcast');
    await waitForHydration(page, 'textarea');
    await expect(page.getByText('Maintenance window number 1', { exact: true })).toBeVisible();

    const { blocking, summary } = await scanPage(page, testInfo, 'admin broadcast history');
    expect(
      blocking,
      `axe violations on the broadcast history:
${summary}`
    ).toHaveLength(0);
  });
});
