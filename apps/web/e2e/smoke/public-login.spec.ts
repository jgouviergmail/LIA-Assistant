/**
 * Public login page — renders with no backend dependency (audit F031).
 *
 * The AuthProvider deliberately skips the /auth/me probe on auth pages. The
 * ONLY allowed API call is the anonymous GET /auth/features capability probe
 * (security program D1): it gates the passkey button and leaks nothing about
 * accounts or sessions. The catch-all (auto fixture) proves nothing else
 * escapes. Selectors are attribute/role based, not text, so the smoke is
 * language-agnostic.
 */
import { test, expect } from '../fixtures';

test.describe('public login page', () => {
  test('renders the credential form with no API call beyond the capability probe', async ({
    page,
  }) => {
    const apiRequests: string[] = [];
    page.on('request', r => {
      if (r.url().includes('/api/v1/')) apiRequests.push(r.url());
    });

    await page.goto('/en/login');

    // The form and its two credential fields are present and interactive.
    await expect(page.locator('input[type="email"]')).toBeVisible();
    await expect(page.locator('input[type="password"]')).toBeVisible();
    await expect(page.locator('button[type="submit"]')).toBeVisible();

    // Auth pages skip the session probe. The anonymous /auth/features
    // capability probe (passkey button gating) is the single tolerated call.
    const unexpected = apiRequests.filter(url => !url.includes('/auth/features'));
    expect(unexpected, `unexpected API calls: ${unexpected.join(', ')}`).toHaveLength(0);
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
