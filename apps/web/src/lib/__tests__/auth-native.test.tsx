/**
 * AuthProvider — the two calls the native shells add.
 *
 * A shell cannot sign in the way a browser does: Google refuses OAuth from an
 * embedded webview, so the authorization URL must reach the SYSTEM browser and
 * the session must come back as a code the WebView spends itself.
 *
 * Only the first half of that is this module's job, and only since the shell
 * decision moved to `navigateToAuthorizationUrl` — the one door all eight OAuth
 * flows go through. What is pinned here is therefore that the challenge reaches
 * the server and that the guarded door is the one used. "The WebView is never
 * navigated to the provider" now lives where it is decided, in
 * `safe-navigation.test.ts`, and applies to connectors and MCP too rather than
 * to sign-in alone.
 */

import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';

import { renderHook, waitFor } from '@/__tests__/test-utils';
import { makeUser } from '@/__tests__/factories';

const { get, post } = vi.hoisted(() => ({ get: vi.fn(), post: vi.fn() }));
vi.mock('@/lib/api-client', () => ({ default: { get, post } }));

vi.mock('@/hooks/useLocalizedRouter', () => ({
  useLocalizedRouter: () => ({ push: vi.fn(), replace: vi.fn(), prefetch: vi.fn(), back: vi.fn() }),
}));

const { navigateToAuthorizationUrl } = vi.hoisted(() => ({
  navigateToAuthorizationUrl: vi.fn(),
}));
vi.mock('@/lib/safe-navigation', () => ({ navigateToAuthorizationUrl }));

const { openInSystemBrowser } = vi.hoisted(() => ({ openInSystemBrowser: vi.fn() }));
vi.mock('@/lib/native/shell', () => ({ openInSystemBrowser }));

import { AuthProvider } from '../auth';
import { useAuth } from '@/hooks/useAuth';

function renderAuth() {
  const rendered = renderHook(() => useAuth(), {
    wrapper: ({ children }) => <AuthProvider>{children}</AuthProvider>,
  });
  return rendered;
}

async function settled(rendered: ReturnType<typeof renderAuth>) {
  await waitFor(() => expect(rendered.result.current.isLoading).toBe(false));
  return rendered;
}

let originalLocation: Location;

beforeEach(() => {
  vi.clearAllMocks();
  originalLocation = window.location;
  Object.defineProperty(window, 'location', {
    value: { pathname: '/fr/dashboard', href: '' },
    writable: true,
    configurable: true,
  });
  get.mockResolvedValue(makeUser({ email: 'user@test.dev' }));
  vi.spyOn(console, 'error').mockImplementation(() => {});
});

afterEach(() => {
  Object.defineProperty(window, 'location', { value: originalLocation, configurable: true });
  vi.restoreAllMocks();
});

describe('initiateGoogleOAuth — from a native shell', () => {
  it('sends the challenge so the callback returns through a deep link', async () => {
    const rendered = await settled(renderAuth());
    get.mockResolvedValue({ authorization_url: 'https://accounts.example/auth' });
    openInSystemBrowser.mockResolvedValue(true);

    await rendered.result.current.initiateGoogleOAuth('challenge-abc');

    expect(get).toHaveBeenLastCalledWith('/auth/google/login', {
      params: { native_challenge: 'challenge-abc' },
    });
  });

  it('leaves through the one guarded door, native or not', async () => {
    const rendered = await settled(renderAuth());
    get.mockResolvedValue({ authorization_url: 'https://accounts.example/auth' });

    await rendered.result.current.initiateGoogleOAuth('challenge-abc');

    // Sign-in used to reach for the shell itself. It no longer does, and that
    // is the point: whether a URL leaves for the system browser is a property
    // of leaving at all, not of this flow. Reintroducing a branch here would
    // put sign-in back out of step with the seven other flows.
    expect(navigateToAuthorizationUrl).toHaveBeenCalledWith(
      'https://accounts.example/auth',
      'google-login'
    );
    expect(openInSystemBrowser).not.toHaveBeenCalled();
  });
});

describe('initiateGoogleOAuth — from a browser', () => {
  it('is unchanged: no challenge, no shell, a plain navigation', async () => {
    const rendered = await settled(renderAuth());
    get.mockResolvedValue({ authorization_url: 'https://accounts.example/auth' });

    await rendered.result.current.initiateGoogleOAuth();

    expect(get).toHaveBeenLastCalledWith('/auth/google/login', undefined);
    expect(openInSystemBrowser).not.toHaveBeenCalled();
    expect(navigateToAuthorizationUrl).toHaveBeenCalledWith(
      'https://accounts.example/auth',
      'google-login'
    );
  });

  it('propagates a failed initiation so the button can report it', async () => {
    const rendered = await settled(renderAuth());
    get.mockRejectedValue(new Error('503'));

    await expect(rendered.result.current.initiateGoogleOAuth()).rejects.toThrow('503');
  });
});

describe('completeNativeSignIn', () => {
  it('spends the code with its verifier and signs the user in', async () => {
    const rendered = await settled(renderAuth());
    post.mockResolvedValue({ user: makeUser({ email: 'native@test.dev' }) });

    const result = await rendered.result.current.completeNativeSignIn('code-1', 'verifier-1');

    expect(post).toHaveBeenCalledWith('/auth/native/callback', {
      code: 'code-1',
      verifier: 'verifier-1',
    });
    expect(result.mfaRequired).toBe(false);
    await waitFor(() => expect(rendered.result.current.user?.email).toBe('native@test.dev'));
  });

  it('reports an unfinished second factor without signing anyone in', async () => {
    const rendered = await settled(renderAuth());
    post.mockResolvedValue({ mfa_required: true });

    const result = await rendered.result.current.completeNativeSignIn('code-1', 'verifier-1');

    expect(result.mfaRequired).toBe(true);
    // No user: the session does not exist yet, and showing one would be a lie
    // the code step would then contradict.
    expect(rendered.result.current.user?.email).not.toBe('native@test.dev');
  });

  it('propagates a refusal, so the landing page can offer a way back', async () => {
    const rendered = await settled(renderAuth());
    post.mockRejectedValue(new Error('401'));

    await expect(
      rendered.result.current.completeNativeSignIn('code-1', 'verifier-1')
    ).rejects.toThrow('401');
  });
});
