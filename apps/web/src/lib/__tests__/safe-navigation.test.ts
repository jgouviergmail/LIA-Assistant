/**
 * SEC-002 — an API-supplied URL must never become code execution.
 *
 * `window.location.href = <value>` is a navigation primitive: with a
 * `javascript:` URL it does not navigate, it runs in the LIA origin with the
 * session cookie in reach. For MCP the value is discovered from metadata
 * published by a server the user added themselves, so it crosses a trust
 * boundary before reaching that line.
 *
 * The backend already refuses non-HTTPS and private-host endpoints; this guard
 * is defence in depth on the primitive itself, so the property holds even for
 * an endpoint that forgets to validate.
 */

import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';

const { isNativeShell, openInSystemBrowser } = vi.hoisted(() => ({
  isNativeShell: vi.fn(() => false),
  openInSystemBrowser: vi.fn(),
}));
vi.mock('@/lib/native/shell', () => ({ isNativeShell, openInSystemBrowser }));

import {
  isSafeRedirectUrl,
  navigateToAuthorizationUrl,
  UnsafeRedirectError,
} from '@/lib/safe-navigation';

vi.mock('@/lib/logger', () => ({
  logger: { error: vi.fn(), warn: vi.fn(), info: vi.fn(), debug: vi.fn() },
}));

describe('isSafeRedirectUrl', () => {
  it.each([
    'https://accounts.google.com/o/oauth2/v2/auth?client_id=x',
    'https://login.microsoftonline.com/common/oauth2/v2.0/authorize',
    'http://localhost:9000/authorize',
    'https://mcp.example.com:8443/authorize?state=abc',
  ])('accepts the legitimate authorization URL %s', url => {
    expect(isSafeRedirectUrl(url)).toBe(true);
  });

  it.each([
    ['javascript:', 'javascript:alert(document.cookie)'],
    ['uppercased javascript:', 'JaVaScRiPt:alert(1)'],
    ['data:', 'data:text/html,<script>alert(1)</script>'],
    ['vbscript:', 'vbscript:msgbox(1)'],
    ['file:', 'file:///etc/passwd'],
    ['blob:', 'blob:https://evil.test/uuid'],
    ['a relative path', '/dashboard'],
    ['a protocol-relative URL', '//evil.test/authorize'],
    ['the empty string', ''],
    ['whitespace only', '   '],
    ['a bare word', 'not-a-url'],
  ])('refuses %s', (_label, url) => {
    expect(isSafeRedirectUrl(url)).toBe(false);
  });

  it.each([
    ['null', null],
    ['undefined', undefined],
    ['a number', 42],
    ['an object', { href: 'https://ok.test' }],
  ])('refuses the non-string value %s', (_label, value) => {
    expect(isSafeRedirectUrl(value)).toBe(false);
  });

  it('refuses a javascript: URL padded with control characters', () => {
    // Browsers strip leading whitespace and C0 controls before resolving the
    // scheme, so a padded payload is still executable — the parser must be the
    // one deciding, not a hand-rolled `startsWith`.
    expect(isSafeRedirectUrl('\n javascript:alert(1)')).toBe(false);
  });
});

describe('navigateToAuthorizationUrl', () => {
  let assigned: string | undefined;

  beforeEach(() => {
    assigned = undefined;
    isNativeShell.mockReturnValue(false);
    openInSystemBrowser.mockReset();
    // jsdom refuses a real cross-origin navigation; intercept the assignment
    // instead, which is exactly the effect under test.
    Object.defineProperty(window, 'location', {
      configurable: true,
      value: {
        get href() {
          return 'https://lia.test/settings';
        },
        set href(value: string) {
          assigned = value;
        },
      },
    });
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('navigates to a legitimate authorization URL', () => {
    navigateToAuthorizationUrl('https://accounts.google.com/o/oauth2/v2/auth', 'google-login');

    expect(assigned).toBe('https://accounts.google.com/o/oauth2/v2/auth');
  });

  it('throws and never navigates on a javascript: URL', () => {
    expect(() => navigateToAuthorizationUrl('javascript:alert(1)', 'mcp-oauth')).toThrow(
      UnsafeRedirectError
    );

    // The assertion that matters: refusing to navigate. A thrown error with the
    // assignment already done would have executed the payload.
    expect(assigned).toBeUndefined();
  });

  it('throws on a missing authorization_url rather than navigating to "undefined"', () => {
    expect(() => navigateToAuthorizationUrl(undefined, 'mcp-oauth')).toThrow(UnsafeRedirectError);
    expect(assigned).toBeUndefined();
  });

  it('carries a message fit to show the user', () => {
    // Every call site funnels this into a toast; a raw stack or an empty
    // message would surface as a broken dialog.
    try {
      navigateToAuthorizationUrl('data:text/html,x', 'mcp-oauth');
      expect.unreachable('should have thrown');
    } catch (error) {
      expect(error).toBeInstanceOf(UnsafeRedirectError);
      expect((error as Error).message).toContain('authorization URL');
    }
  });
});

describe('navigateToAuthorizationUrl — inside a native shell', () => {
  /**
   * Eight flows leave for an authorization server, and every one of them goes
   * through this function: connectors, MCP, bulk connect, reconnection, and
   * sign-in. Google refuses OAuth from an embedded webview outright, so a
   * WebView navigation ends the flow before it starts — for all eight.
   *
   * Deciding it HERE rather than at each call site is what makes that true
   * without eight remembered branches. The assertion that carries the whole
   * point is the negative one: the location is never assigned.
   */
  let assigned: string | undefined;

  beforeEach(() => {
    assigned = undefined;
    openInSystemBrowser.mockReset();
    isNativeShell.mockReturnValue(true);
    Object.defineProperty(window, 'location', {
      configurable: true,
      value: {
        get href() {
          return 'https://lia.test/settings';
        },
        set href(value: string) {
          assigned = value;
        },
      },
    });
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('hands the URL to the system browser and never navigates the WebView', async () => {
    openInSystemBrowser.mockResolvedValue(true);

    navigateToAuthorizationUrl('https://accounts.google.com/o/oauth2/v2/auth', 'oauth-gmail');
    await vi.waitFor(() => expect(openInSystemBrowser).toHaveBeenCalled());

    expect(openInSystemBrowser).toHaveBeenCalledWith(
      'https://accounts.google.com/o/oauth2/v2/auth'
    );
    expect(assigned).toBeUndefined();
  });

  it('falls back to navigating when no shell takes the URL', async () => {
    openInSystemBrowser.mockResolvedValue(false);

    navigateToAuthorizationUrl('https://accounts.google.com/o/oauth2/v2/auth', 'oauth-gmail');

    // Better a flow the provider may refuse than a button that does nothing.
    await vi.waitFor(() =>
      expect(assigned).toBe('https://accounts.google.com/o/oauth2/v2/auth')
    );
  });

  it('falls back when the shell call itself fails', async () => {
    openInSystemBrowser.mockRejectedValue(new Error('bridge gone'));

    navigateToAuthorizationUrl('https://accounts.google.com/o/oauth2/v2/auth', 'oauth-gmail');

    await vi.waitFor(() =>
      expect(assigned).toBe('https://accounts.google.com/o/oauth2/v2/auth')
    );
  });

  it('still refuses an unsafe URL before the shell ever sees it', () => {
    expect(() => navigateToAuthorizationUrl('javascript:alert(1)', 'mcp-oauth')).toThrow(
      UnsafeRedirectError
    );

    // The guard is the reason this function exists; a shell must not become a
    // way around it.
    expect(openInSystemBrowser).not.toHaveBeenCalled();
    expect(assigned).toBeUndefined();
  });
});
