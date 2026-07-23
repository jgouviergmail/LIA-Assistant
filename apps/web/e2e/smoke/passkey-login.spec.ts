/**
 * Passkey login — hermetic ceremony proof (security program D1, Lot 1).
 *
 * Chromium-only: the ceremony runs against a CDP virtual authenticator
 * (resident key + user verification), so a REAL `navigator.credentials.get`
 * exercises the full browser glue — options parsing (base64url → buffers),
 * the WebAuthn prompt, and assertion serialization back to base64url — while
 * the API stays fully mocked (catch-all + specific routes, zero backend).
 *
 * The MFA feature gate itself (button hidden when the instance reports
 * mfa_enabled=false) is covered per-flag here too.
 */
import { webcrypto } from 'node:crypto';
import { test, expect } from '../fixtures';
import { dashboardShellMocks } from '../fixtures/dashboard-shell';
import { makeTestUser } from '../fixtures/test-user';

const AUTH_OPTIONS = JSON.stringify({
  challenge: 'ZTJlLWNoYWxsZW5nZQ', // base64url("e2e-challenge")
  rpId: 'localhost',
  timeout: 300_000,
  userVerification: 'required',
});

/** Generate a fresh P-256 private key (PKCS8, standard base64) for CDP. */
async function generatePrivateKeyB64(): Promise<string> {
  const keyPair = await webcrypto.subtle.generateKey(
    { name: 'ECDSA', namedCurve: 'P-256' },
    true,
    ['sign', 'verify']
  );
  const pkcs8 = await webcrypto.subtle.exportKey('pkcs8', keyPair.privateKey);
  return Buffer.from(pkcs8).toString('base64');
}

test.describe('passkey login', () => {
  test('the passkey button is hidden when the instance has MFA disabled', async ({
    page,
    mockApi,
  }) => {
    await mockApi([{ url: '**/api/v1/auth/features', json: { mfa_enabled: false } }]);
    await page.goto('/en/login');

    await expect(page.locator('input[type="email"]')).toBeVisible();
    await expect(page.getByRole('button', { name: 'Sign in with a passkey' })).toHaveCount(0);
  });

  test('the passkey button renders when the instance has MFA enabled', async ({
    page,
    mockApi,
  }) => {
    await mockApi([{ url: '**/api/v1/auth/features', json: { mfa_enabled: true } }]);
    await page.goto('/en/login');

    await expect(page.getByRole('button', { name: 'Sign in with a passkey' })).toBeVisible();
  });

  test('a resident-key ceremony signs in and lands on the dashboard', async ({
    page,
    mockApi,
    browserName,
    baseURL,
  }) => {
    test.skip(browserName !== 'chromium', 'CDP virtual authenticator is Chromium-only');

    // WebAuthn refuses an IP-literal rpId, and CI serves the app on
    // 127.0.0.1 (IPv4-only healthcheck of the standalone server). Same
    // server — but the CEREMONY page must live on `localhost` so the
    // mocked rpId 'localhost' is valid for the page origin.
    const loginURL = new URL('/en/login', baseURL);
    if (loginURL.hostname === '127.0.0.1') loginURL.hostname = 'localhost';

    // --- Virtual authenticator with a pre-enrolled discoverable credential.
    const cdp = await page.context().newCDPSession(page);
    await cdp.send('WebAuthn.enable');
    const { authenticatorId } = (await cdp.send('WebAuthn.addVirtualAuthenticator', {
      options: {
        protocol: 'ctap2',
        transport: 'internal',
        hasResidentKey: true,
        hasUserVerification: true,
        isUserVerified: true,
        automaticPresenceSimulation: true,
      },
    })) as { authenticatorId: string };

    await cdp.send('WebAuthn.addCredential', {
      authenticatorId,
      credential: {
        credentialId: Buffer.from('cred-e2e-1').toString('base64'),
        isResidentCredential: true,
        rpId: 'localhost',
        privateKey: await generatePrivateKeyB64(),
        userHandle: Buffer.from('user-e2e-1').toString('base64'),
        signCount: 0,
      },
    });

    // --- Hermetic API: capture what the app sends to the verify endpoint.
    const user = makeTestUser();
    let verifyBody: {
      challenge_id?: string;
      credential?: { rawId?: string; response?: { signature?: string } };
    } | null = null;

    await mockApi([
      ...dashboardShellMocks,
      { url: '**/api/v1/auth/features', json: { mfa_enabled: true } },
      { url: '**/api/v1/auth/me', json: user },
      {
        url: '**/api/v1/auth/webauthn/authenticate/options',
        method: 'POST',
        json: { challenge_id: 'ch-e2e-1', options: AUTH_OPTIONS },
      },
      {
        url: '**/api/v1/auth/webauthn/authenticate/verify',
        method: 'POST',
        handler: async route => {
          verifyBody = route.request().postDataJSON();
          await route.fulfill({
            status: 200,
            contentType: 'application/json',
            body: JSON.stringify({ user, message: 'ok' }),
          });
        },
      },
    ]);

    // Diagnostics: ceremony endpoints hit + browser console errors.
    const ceremonyCalls: string[] = [];
    page.on('request', r => {
      if (r.url().includes('/auth/webauthn/')) ceremonyCalls.push(`${r.method()} ${r.url()}`);
    });
    const consoleErrors: string[] = [];
    page.on('console', message => {
      if (message.type() === 'error') consoleErrors.push(message.text());
    });

    await page.goto(loginURL.toString());

    // The armed conditional-UI ceremony may auto-complete with the virtual
    // authenticator before the explicit click; both paths exercise the same
    // ceremony glue, so tolerate either and assert the outcome.
    const button = page.getByRole('button', { name: 'Sign in with a passkey' });
    try {
      await button.click({ timeout: 5_000 });
    } catch {
      // Conditional path already consumed the ceremony.
    }

    await expect
      .poll(() => ceremonyCalls.length, {
        message: `ceremony endpoints never called — console errors: ${consoleErrors.join(' | ')}`,
        timeout: 15_000,
      })
      .toBeGreaterThanOrEqual(1);

    await expect
      .poll(() => Boolean(verifyBody), {
        message:
          `verify never reached — ceremony calls: ${ceremonyCalls.join(', ')} — ` +
          `console errors: ${consoleErrors.join(' | ')}`,
        timeout: 30_000,
      })
      .toBe(true);

    await page.waitForURL('**/dashboard**');

    expect(verifyBody).not.toBeNull();
    expect(verifyBody!.challenge_id).toBe('ch-e2e-1');
    // rawId is the virtual credential id, base64url-encoded by our serializer.
    expect(verifyBody!.credential?.rawId).toBe(
      Buffer.from('cred-e2e-1').toString('base64url')
    );
    expect(verifyBody!.credential?.response?.signature).toBeTruthy();
  });
});
