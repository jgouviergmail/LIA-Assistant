/**
 * The web app's side of the native shells.
 *
 * The verifier is the whole security argument: the return trip rides a custom
 * scheme any application can claim, so an intercepted deep link must be
 * useless. These tests pin that the verifier never leaves the page, that the
 * challenge is what the API validates, and that a browser — where none of this
 * applies — keeps its ordinary flow.
 */

import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';

import {
  beginNativeSignIn,
  isNativeShell,
  openInSystemBrowser,
  takeNativeVerifier,
} from '../shell';

vi.mock('@/lib/logger', () => ({
  logger: { debug: vi.fn(), info: vi.fn(), warn: vi.fn(), error: vi.fn() },
}));

function installShell(plugin?: { openExternal: ReturnType<typeof vi.fn> }) {
  (window as unknown as { Capacitor?: unknown }).Capacitor = {
    isNativePlatform: () => true,
    Plugins: plugin ? { LiaShell: plugin } : {},
  };
}

beforeEach(() => {
  sessionStorage.clear();
  vi.clearAllMocks();
});

afterEach(() => {
  delete (window as unknown as { Capacitor?: unknown }).Capacitor;
});

describe('isNativeShell', () => {
  it('is false in a plain browser', () => {
    expect(isNativeShell()).toBe(false);
  });

  it('is true when the bridge injected itself', () => {
    installShell();

    expect(isNativeShell()).toBe(true);
  });

  it('is false when Capacitor exists but says it is not native', () => {
    (window as unknown as { Capacitor?: unknown }).Capacitor = {
      isNativePlatform: () => false,
    };

    expect(isNativeShell()).toBe(false);
  });
});

describe('beginNativeSignIn', () => {
  it('returns a challenge the API will accept', async () => {
    const challenge = await beginNativeSignIn();

    // RFC 7636 bounds and alphabet — the same the endpoint validates against.
    expect(challenge).toMatch(/^[A-Za-z0-9\-_]+$/);
    expect(challenge.length).toBeGreaterThanOrEqual(43);
    expect(challenge.length).toBeLessThanOrEqual(128);
  });

  it('keeps the verifier, and sends only its hash', async () => {
    const challenge = await beginNativeSignIn();
    const verifier = sessionStorage.getItem('lia.native.verifier');

    expect(verifier).toBeTruthy();
    // If the challenge were the verifier, an intercepted deep link would be
    // enough to redeem the code — which is the attack this prevents.
    expect(challenge).not.toBe(verifier);
  });

  it('draws a fresh verifier every time', async () => {
    await beginNativeSignIn();
    const first = sessionStorage.getItem('lia.native.verifier');
    await beginNativeSignIn();
    const second = sessionStorage.getItem('lia.native.verifier');

    expect(first).not.toBe(second);
  });

  it('produces the SHA-256 the server will compare against', async () => {
    const challenge = await beginNativeSignIn();
    const verifier = sessionStorage.getItem('lia.native.verifier') as string;

    const digest = await crypto.subtle.digest('SHA-256', new TextEncoder().encode(verifier));
    const expected = btoa(String.fromCharCode(...new Uint8Array(digest)))
      .replace(/\+/g, '-')
      .replace(/\//g, '_')
      .replace(/=+$/, '');

    expect(challenge).toBe(expected);
  });
});

describe('takeNativeVerifier', () => {
  it('returns the verifier once and then forgets it', async () => {
    await beginNativeSignIn();

    const first = takeNativeVerifier();
    const second = takeNativeVerifier();

    expect(first).toBeTruthy();
    // A second read must find nothing: the code it matches is single-use too,
    // and a lingering verifier is a credential with no purpose left.
    expect(second).toBeNull();
  });

  it('returns null when no sign-in was started', () => {
    expect(takeNativeVerifier()).toBeNull();
  });
});

describe('openInSystemBrowser', () => {
  it('hands the URL to the shell', async () => {
    const openExternal = vi.fn().mockResolvedValue(undefined);
    installShell({ openExternal });

    const handled = await openInSystemBrowser('https://accounts.example/auth');

    expect(handled).toBe(true);
    expect(openExternal).toHaveBeenCalledWith({ url: 'https://accounts.example/auth' });
  });

  it('reports that nobody took it when there is no shell', async () => {
    const handled = await openInSystemBrowser('https://accounts.example/auth');

    expect(handled).toBe(false);
  });

  it('reports failure rather than throwing, so the caller can fall back', async () => {
    const openExternal = vi.fn().mockRejectedValue(new Error('no browser'));
    installShell({ openExternal });

    await expect(openInSystemBrowser('https://accounts.example/auth')).resolves.toBe(false);
  });
});
