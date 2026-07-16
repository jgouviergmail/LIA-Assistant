/**
 * Accessibility smoke — axe-core WCAG 2.x A/AA scans (audit F031, AC-002).
 *
 * Runs the industry-standard axe engine against stable pages in a real browser,
 * complementing the static jsx-a11y ratchet with actual computed-tree analysis
 * (names, roles, ARIA, focus order, contrast). The login page is fully
 * data-independent; the dashboard is scanned with the hermetic auth harness.
 *
 * Policy (AC-002): EVERY `critical`/`serious` violation is blocking —
 * including `color-contrast`. The theme tokens are AA-proven at the unit level
 * (src/styles/__tests__/design-contrast.guard.test.ts covers all 5 themes ×
 * light/dark × hover/tint states); this browser scan is the end-to-end check
 * on real rendered pages. Per-node details are archived as JSON attachments
 * by the shared `scanPage` helper (see ./scan.ts).
 *
 * `moderate`/`minor` are surfaced by the engine but do not fail the smoke yet.
 * Deeper journeys (chat, settings, spaces, admin, reflow/zoom) live in
 * ./axe-journeys.spec.ts.
 */
import { test, expect, type MockRoute } from '../fixtures';
import { scanPage } from './scan';

const dashboardData: MockRoute[] = [
  { url: '**/api/v1/briefing/cards', json: { cards: {} } },
  {
    url: '**/api/v1/briefing/synthesis',
    json: { greeting: { text: 'Welcome back', generated_at: null, usage: null }, synthesis: null },
  },
  { url: '**/api/v1/usage/**', json: {} },
];

test.describe('accessibility smoke (axe WCAG 2.x A/AA)', () => {
  test('login page has no critical/serious violations (contrast included)', async ({
    page,
  }, testInfo) => {
    await page.goto('/en/login');
    await expect(page.locator('button[type="submit"]')).toBeVisible();

    const { blocking, summary } = await scanPage(page, testInfo, '/login');
    expect(blocking, `axe violations on /login:\n${summary}`).toHaveLength(0);
  });

  test('authenticated dashboard has no critical/serious violations (contrast included)', async ({
    page,
    authenticate,
    mockApi,
  }, testInfo) => {
    await authenticate();
    await mockApi(dashboardData);
    await page.goto('/en/dashboard');
    await expect(page.getByRole('main')).toBeVisible();

    const { blocking, summary } = await scanPage(page, testInfo, '/dashboard');
    expect(blocking, `axe violations on /dashboard:\n${summary}`).toHaveLength(0);
  });
});
