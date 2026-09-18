/**
 * The sandbox network panel — what a script may reach, and what the person
 * allowed (ADR-298).
 *
 * Three claims only a browser can prove, each paid for once:
 *
 * - a connector host reads with its BRAND name and the token's origin, an
 *   operator host with the instance's own words — the unit tests see the i18n
 *   mock echo keys, so only a real render shows what a person reads;
 * - the two edits are one click and one exact write each: the scope switch
 *   (`PATCH /sandbox/egress-grants/{id}` with `share_turn_data`) and the
 *   revoke (`DELETE /sandbox/egress-grants/{id}`), the row leaving the list
 *   at once and the exact total following;
 * - the whole section fits a 320 px phone without a horizontal scroll.
 */
import { test, expect, type MockRoute } from '../fixtures';
import { awaitStyledPage, expectNoOverflow } from './overflow-report';

const GRANT_WITH_DATA = '00000000-0000-4000-8000-0000000000e1';
const GRANT_WITHOUT_DATA = '00000000-0000-4000-8000-0000000000e2';

/** Mirrors `AppConfig` (src/hooks/useAppConfig.ts) with the egress flag ON. */
const APP_CONFIG = {
  sse: { heartbeat_interval_seconds: 30 },
  rate_limits: { enabled: false, per_minute: 60, burst: 10 },
  i18n: { supported_languages: ['en', 'fr', 'de', 'es', 'it', 'zh'], default_language: 'en' },
  features: {
    tool_approval_enabled: false,
    attachments_enabled: true,
    rag_spaces_enabled: true,
    rag_spaces_embedding_model: 'text-embedding-3-small',
    journals_enabled: false,
    python_sandbox_egress_enabled: true,
  },
  api_version: 'v1',
};

/** Mirrors `ReachableHostsResponse` (python_sandbox/egress/schemas.py). */
const REACHABLE = {
  items: [
    { host: 'api.search.brave.com', status: 'connector', connector: 'brave_search' },
    { host: 'status.example.org', status: 'operator', connector: null },
  ],
  ask_enabled: true,
};

/** Mirrors `EgressGrantListResponse` — the exact total exceeds the page on purpose. */
const GRANTS = {
  items: [
    {
      id: GRANT_WITH_DATA,
      host: 'feeds.example.net',
      share_turn_data: true,
      created_at: '2026-09-17T09:12:00Z',
      last_used_at: '2026-09-18T08:03:00Z',
    },
    {
      id: GRANT_WITHOUT_DATA,
      host: 'weather.example.com',
      share_turn_data: false,
      created_at: '2026-09-16T18:40:00Z',
      last_used_at: null,
    },
  ],
  total: 3,
  limit: 50,
  offset: 0,
  max_limit: 50,
  max_per_user: 50,
};

const ROUTES: MockRoute[] = [
  { url: '**/api/v1/config', json: APP_CONFIG },
  { url: '**/api/v1/sandbox/egress-grants/reachable', method: 'GET', json: REACHABLE },
  { url: '**/api/v1/sandbox/egress-grants?*', method: 'GET', json: GRANTS },
];

test.describe('sandbox network settings panel', () => {
  test('hosts read with their origin, permissions with their scope, the cut stated', async ({
    page,
    authenticate,
    mockApi,
  }) => {
    await authenticate({ language: 'en' });
    await mockApi(ROUTES);
    await page.goto('/en/dashboard/settings?section=sandbox-egress');

    await expect(page.getByRole('heading', { name: 'Sandbox network' })).toBeVisible({
      timeout: 20_000,
    });

    // A connector host names the brand and the token's origin; an operator
    // host names the instance. The raw connector key never reaches the screen.
    await expect(page.getByText('api.search.brave.com')).toBeVisible();
    await expect(page.getByText('Your Brave Search connector')).toBeVisible();
    await expect(page.getByText('brave_search')).toHaveCount(0);
    await expect(page.getByText('status.example.org')).toBeVisible();
    await expect(page.getByText('Allowed by this instance')).toBeVisible();

    // Each permission carries its stored scope, and the exact total (3) is
    // stated against the two rows the page holds (ADR-185).
    const switches = page.getByRole('switch');
    await expect(switches).toHaveCount(2);
    await expect(switches.nth(0)).toHaveAttribute('aria-checked', 'true');
    await expect(switches.nth(1)).toHaveAttribute('aria-checked', 'false');
    await expect(page.getByText('1 more permission is not shown here.')).toBeVisible();
    await expect(page.getByText('3 / 50 permissions')).toBeVisible();
  });

  test('changing a scope and revoking are one click and one exact write each', async ({
    page,
    authenticate,
    mockApi,
  }) => {
    const writes: Array<{ method: string; url: string; body: unknown }> = [];
    await authenticate({ language: 'en' });
    await mockApi([
      ...ROUTES,
      {
        url: `**/api/v1/sandbox/egress-grants/${GRANT_WITH_DATA}`,
        method: 'PATCH',
        handler: async route => {
          writes.push({
            method: 'PATCH',
            url: route.request().url(),
            body: route.request().postDataJSON(),
          });
          await route.fulfill({
            status: 200,
            contentType: 'application/json',
            body: JSON.stringify({ ...GRANTS.items[0], share_turn_data: false }),
          });
        },
      },
      {
        url: `**/api/v1/sandbox/egress-grants/${GRANT_WITHOUT_DATA}`,
        method: 'DELETE',
        handler: async route => {
          writes.push({ method: 'DELETE', url: route.request().url(), body: null });
          await route.fulfill({ status: 204, body: '' });
        },
      },
    ]);
    await page.goto('/en/dashboard/settings?section=sandbox-egress');
    await expect(page.getByText('feeds.example.net')).toBeVisible({ timeout: 20_000 });

    await page.getByRole('switch').nth(0).click();
    await expect.poll(() => writes.length, { timeout: 10_000 }).toBe(1);
    expect(writes[0].method).toBe('PATCH');
    expect(writes[0].url).toContain(`/api/v1/sandbox/egress-grants/${GRANT_WITH_DATA}`);
    expect(writes[0].body).toEqual({ share_turn_data: false });
    await expect(page.getByRole('switch').nth(0)).toHaveAttribute('aria-checked', 'false');

    // The revoke is named with its host (a11y — inline at this width, a « ⋮ »
    // menu on a phone); the row leaves at once and the exact total follows.
    await page.getByRole('button', { name: 'Revoke weather.example.com' }).click();
    await expect.poll(() => writes.length, { timeout: 10_000 }).toBe(2);
    expect(writes[1].method).toBe('DELETE');
    expect(writes[1].url).toContain(`/api/v1/sandbox/egress-grants/${GRANT_WITHOUT_DATA}`);
    await expect(page.getByText('weather.example.com')).toHaveCount(0);
    await expect(page.getByText('2 / 50 permissions')).toBeVisible();
  });

  test('the whole panel fits a 320 px phone without a horizontal scroll', async ({
    page,
    authenticate,
    mockApi,
  }) => {
    await authenticate({ language: 'en' });
    await mockApi(ROUTES);
    await page.setViewportSize({ width: 320, height: 800 });
    await page.goto('/en/dashboard/settings?section=sandbox-egress');
    await awaitStyledPage(page, '/dashboard/settings?section=sandbox-egress @320px');

    await expect(page.getByText('feeds.example.net')).toBeVisible({ timeout: 20_000 });
    await expect(page.getByText('3 / 50 permissions')).toBeVisible();

    await expectNoOverflow(page, 'sandbox network section at 320px');
  });
});
