/**
 * Public login page — renders with zero backend calls (audit F031).
 *
 * The AuthProvider deliberately skips the /auth/me probe on auth pages, so the
 * login page is fully data-independent: the catch-all (auto fixture) proves no
 * API request escapes. Selectors are attribute/role based, not text, so the
 * smoke is language-agnostic.
 */
import { test, expect } from '../fixtures';

test.describe('public login page', () => {
  test('renders the credential form without any API call', async ({ page }) => {
    const apiRequests: string[] = [];
    page.on('request', (r) => {
      if (r.url().includes('/api/v1/')) apiRequests.push(r.url());
    });

    await page.goto('/en/login');

    // The form and its two credential fields are present and interactive.
    await expect(page.locator('input[type="email"]')).toBeVisible();
    await expect(page.locator('input[type="password"]')).toBeVisible();
    await expect(page.locator('button[type="submit"]')).toBeVisible();

    // Auth pages skip the session probe — no backend dependency at all.
    expect(apiRequests, `unexpected API calls: ${apiRequests.join(', ')}`).toHaveLength(0);
  });

  test('lets the user type credentials', async ({ page }) => {
    await page.goto('/en/login');
    await page.locator('input[type="email"]').fill('e2e.user@example.test');
    await page.locator('input[type="password"]').fill('correct horse battery');
    await expect(page.locator('input[type="email"]')).toHaveValue('e2e.user@example.test');
  });

  test('remember-me checkbox is named, keyboard-reachable and toggleable (F012)', async ({
    page,
  }) => {
    await page.goto('/en/login');

    // Role + real translated name proves the programmatic label association
    // in an actual browser accessibility tree (not just static analysis).
    const rememberMe = page.getByRole('checkbox', {
      name: 'Remember me (30 days instead of 7)',
    });
    await expect(rememberMe).toBeVisible();

    await rememberMe.focus();
    await expect(rememberMe).toBeFocused();

    await page.keyboard.press('Space');
    await expect(rememberMe).toBeChecked();
  });
});
