/**
 * Sign-in with the bot check (ADR-364) — hermetic.
 *
 * Cloudflare's loader is replaced by a stand-in that solves the check at once
 * and records what the page asked of it; the API is mocked. Proves, in a real
 * browser and from the keyboard: the widget is rendered for the sign-in door
 * with the instance's site key, the token reaches the API in its header, a
 * refused check is NAMED (never blamed on the password), and the widget starts
 * over because the API spent the token.
 */
import { test, expect, waitForHydration } from '../fixtures';

const SITE_KEY = '1x00000000000000000000AA';
const DUMMY_TOKEN = 'XXXX.DUMMY.TOKEN.XXXX';

interface TurnstileProbe {
  renders: number;
  resets: number;
  last?: { action: string; sitekey: string };
}

declare global {
  interface Window {
    __turnstile?: TurnstileProbe;
  }
}

/** Stands in for https://challenges.cloudflare.com/turnstile/v0/api.js. */
const FAKE_TURNSTILE = `
  window.__turnstile = { renders: 0, resets: 0 };
  window.turnstile = {
    render: function (container, options) {
      window.__turnstile.renders += 1;
      window.__turnstile.last = { action: options.action, sitekey: options.sitekey };
      setTimeout(function () { options.callback(${JSON.stringify(DUMMY_TOKEN)}); }, 0);
      return 'widget-' + window.__turnstile.renders;
    },
    reset: function () { window.__turnstile.resets += 1; },
    remove: function () {},
  };
`;

test.describe('sign-in with the bot check (ADR-364)', () => {
  test('sends the token, names a refused check, and asks for a new token', async ({
    page,
    mockApi,
  }) => {
    await page.route('https://challenges.cloudflare.com/**', route =>
      route.fulfill({ contentType: 'application/javascript', body: FAKE_TURNSTILE })
    );
    const sentTokens: (string | null)[] = [];
    await mockApi([
      {
        url: '**/api/v1/auth/features',
        json: {
          mfa_enabled: false,
          federated_signin_enabled: true,
          terms_required: false,
          terms_version: '',
          turnstile_site_key: SITE_KEY,
        },
      },
      {
        url: '**/api/v1/auth/login',
        method: 'POST',
        handler: async route => {
          sentTokens.push(route.request().headers()['x-lia-turnstile-response'] ?? null);
          await route.fulfill({ status: 403, json: { detail: { error: 'turnstile_failed' } } });
        },
      },
    ]);

    await page.goto('/en/login');
    await waitForHydration(page);
    await expect.poll(() => page.evaluate(() => window.__turnstile?.last ?? null)).toEqual({
      action: 'login',
      sitekey: SITE_KEY,
    });

    await page.locator('input[type="email"]').fill('e2e.user@example.test');
    await page.locator('input[type="password"]').fill('correct horse battery');
    await page.locator('input[type="password"]').press('Enter');

    await expect(page.getByText('The anti-robot check failed. Try again.')).toBeVisible();
    await expect(page.getByText('Invalid email or password')).toHaveCount(0);
    expect(sentTokens).toEqual([DUMMY_TOKEN]);
    await expect.poll(() => page.evaluate(() => window.__turnstile?.resets ?? 0)).toBe(1);
    // The check is a named region the assistive technologies can announce.
    await expect(page.getByRole('group', { name: 'Anti-robot check' })).toBeAttached();
  });

  test('still sends the sign-in when Cloudflare cannot be reached', async ({ page, mockApi }) => {
    // An outage reaches the browser too: the widget never loads. The sign-in goes
    // without a token, and the API decides from its own view of Cloudflare.
    await page.route('https://challenges.cloudflare.com/**', route => route.abort('failed'));
    const sentTokens: (string | null)[] = [];
    await mockApi([
      {
        url: '**/api/v1/auth/features',
        json: {
          mfa_enabled: false,
          federated_signin_enabled: true,
          terms_required: false,
          terms_version: '',
          turnstile_site_key: SITE_KEY,
        },
      },
      {
        url: '**/api/v1/auth/login',
        method: 'POST',
        handler: async route => {
          sentTokens.push(route.request().headers()['x-lia-turnstile-response'] ?? null);
          await route.fulfill({ status: 403, json: { detail: { error: 'turnstile_failed' } } });
        },
      },
    ]);

    await page.goto('/en/login');
    await waitForHydration(page);
    await expect(
      page.getByText('The anti-robot check could not load. You can still sign in.')
    ).toBeVisible();

    await page.locator('input[type="email"]').fill('e2e.user@example.test');
    await page.locator('input[type="password"]').fill('correct horse battery');
    await page.locator('input[type="password"]').press('Enter');

    await expect.poll(() => sentTokens).toEqual([null]);
    // Cloudflare answered the API, so the block is this browser's: say how to lift it.
    await expect(page.getByText(/Allow challenges\.cloudflare\.com for this site/)).toBeVisible();
  });
});
