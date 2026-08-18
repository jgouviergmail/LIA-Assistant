/**
 * Settings deep links — `?section=` opens the section's pane.
 *
 * The settings page is a master-detail shell: a rail of sections beside a pane
 * that mounts exactly ONE of them. `?section=` is both the deep-link API and
 * the selection state, so the contract a browser must prove changed with the
 * shell: the pane mounts the section OPEN (no accordion to expand any more),
 * the URL KEEPS the token (a reload or a share lands on the same pane), and an
 * unknown token falls back to the overview with a clean URL.
 */
import { test, expect, type MockRoute } from '../fixtures';

/**
 * Deliberately MINIMAL.
 *
 * Mocking each settings subsystem turned out to make the run erratic: a broad
 * pattern such as `**​/api/v1/connectors/**` shadows narrower shell mocks
 * (Playwright routes are LIFO), and the sections then render — or not —
 * depending on which one won. The routing mechanism under test does not need
 * any of that data: unmocked endpoints hit the 501 catch-all, which every
 * section is built to survive (that is what `FeatureErrorBoundary` is for).
 */
const ROUTES: MockRoute[] = [
  { url: '**/api/v1/connectors', json: { connectors: [] } },
  { url: '**/api/v1/scheduled-actions**', json: { actions: [], total: 0 } },
  { url: '**/api/v1/usage/**', json: {} },
  // `OpenLoopsSection` self-gates on this flag and renders NOTHING without it,
  // so the commitments case below needs the instance to declare the capability.
  // Narrow and additive: every other section reads flags that stay absent here,
  // and an absent flag is falsy exactly as it was when nothing answered.
  {
    url: '**/api/v1/config',
    json: {
      sse: { heartbeat_interval_seconds: 30 },
      rate_limits: { enabled: false, per_minute: 60, burst: 10 },
      i18n: { supported_languages: ['fr', 'en'], default_language: 'en' },
      features: { open_loops_enabled: true },
      api_version: 'v1',
    },
  },
  { url: '**/api/v1/open-loops**', json: { items: [], total: 0 } },
];

/**
 * Tokens exercised here, paired with the anchor value the pane must mount.
 *
 * Kept explicit rather than imported from the app: an e2e that reads the very
 * table it verifies would still pass if that table drifted.
 *
 * Coverage is deliberately partial — the sample spans both former tabs plus an
 * instance-gated section; the completeness of the table itself is asserted in
 * `lib/__tests__/settings-sections.test.ts`.
 */
const CASES = [
  { token: 'connectors', value: 'connectors' },
  { token: 'voice-mode', value: 'voice-mode' },
  { token: 'personality', value: 'personality' },
  { token: 'memories', value: 'memories' },
  { token: 'interests', value: 'interests' },
  { token: 'scheduled-actions', value: 'scheduled-actions' },
  { token: 'journals', value: 'journals' },
  // The destination of the dashboard's "For you" commitments card. That card
  // linked to the bare settings page until 2026-08-03 — the exact failure this
  // file was written for. Pinned so the link keeps arriving.
  { token: 'open-loops', value: 'open-loops' },
] as const;

test.describe('settings deep links', () => {
  for (const { token, value } of CASES) {
    test(`?section=${token} opens its pane`, async ({ page, authenticate, mockApi }) => {
      await authenticate({ language: 'fr' });
      await mockApi(ROUTES);
      await page.goto(`/fr/dashboard/settings?section=${token}`);

      // The generous timeout is the cost of the dev server, not a product
      // signal; against the CI production build this resolves immediately.
      const section = page.locator(`#settings-section-${value}`);
      await expect(section, `${token} must mount its section`).toBeVisible({ timeout: 20_000 });

      // Master-detail: the pane holds exactly ONE section.
      await expect(page.locator('[id^="settings-section-"]')).toHaveCount(1);

      // The token is selection state now: it STAYS in the URL, so a reload or
      // a shared link lands on the same pane.
      expect(new URL(page.url()).searchParams.get('section')).toBe(token);
    });
  }

  test('a reload lands on the same section', async ({ page, authenticate, mockApi }) => {
    await authenticate({ language: 'fr' });
    await mockApi(ROUTES);
    await page.goto('/fr/dashboard/settings?section=personality');
    await expect(page.locator('#settings-section-personality')).toBeVisible({ timeout: 20_000 });

    await page.reload();
    await expect(page.locator('#settings-section-personality')).toBeVisible({ timeout: 20_000 });
  });

  test('an unknown token lands on the overview with a clean URL', async ({
    page,
    authenticate,
    mockApi,
  }) => {
    // A stale bookmark must not throw, and must not open something arbitrary.
    await authenticate({ language: 'fr' });
    await mockApi(ROUTES);
    await page.goto('/fr/dashboard/settings?section=does-not-exist');

    await expect(page.getByRole('heading', { level: 1 })).toBeVisible();
    // No pane is mounted: the overview cards are the landing.
    await expect(page.locator('[id^="settings-section-"]')).toHaveCount(0);
    await expect
      .poll(async () => new URL(page.url()).searchParams.get('section'), { timeout: 10_000 })
      .toBeNull();
  });
});
