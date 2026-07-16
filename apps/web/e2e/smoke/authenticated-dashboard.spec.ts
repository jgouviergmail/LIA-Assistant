/**
 * Authenticated dashboard — hermetic auth + a full login journey (audit F031).
 *
 * Proves the interception harness end to end: with /auth/me mocked the
 * protected dashboard renders (its <main> landmark), and a real form-driven
 * login (POST /auth/login → redirect → /auth/me) lands the user on it. No
 * backend, LLM, or paid provider is contacted — the catch-all fails any
 * un-mocked call loudly.
 */
import { test, expect, makeTestUser, type MockRoute } from '../fixtures';

/** Minimal, shape-correct briefing/usage mocks so the dashboard renders clean. */
const dashboardData: MockRoute[] = [
  { url: '**/api/v1/briefing/cards', json: { cards: {} } },
  {
    url: '**/api/v1/briefing/synthesis',
    json: { greeting: { text: 'Welcome back', generated_at: null, usage: null }, synthesis: null },
  },
  { url: '**/api/v1/usage/**', json: {} },
];

test.describe('authenticated dashboard', () => {
  test('renders the protected shell when the session is valid', async ({
    page,
    authenticate,
    mockApi,
  }) => {
    await authenticate();
    await mockApi(dashboardData);

    await page.goto('/en/dashboard');

    // The dashboard layout's <main> landmark is the stable, language-agnostic
    // anchor. Its presence proves we were NOT bounced to login.
    await expect(page.getByRole('main')).toBeVisible();
    await expect(page.getByRole('navigation').first()).toBeVisible();
    expect(new URL(page.url()).pathname).toContain('/dashboard');
  });

  test('a form login lands the user on the dashboard', async ({ page, mockApi }) => {
    const user = makeTestUser();
    await mockApi([
      { url: '**/api/v1/auth/login', method: 'POST', json: { user } },
      { url: '**/api/v1/auth/me', json: user },
      ...dashboardData,
    ]);

    await page.goto('/en/login');
    await page.locator('input[type="email"]').fill(user.email);
    await page.locator('input[type="password"]').fill('correct horse battery');
    await page.locator('button[type="submit"]').click();

    await page.waitForURL('**/dashboard', { timeout: 15_000 });
    await expect(page.getByRole('main')).toBeVisible();
  });
});
