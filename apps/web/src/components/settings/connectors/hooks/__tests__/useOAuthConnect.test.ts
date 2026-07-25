/**
 * useOAuthConnect — the first leg of every Google/Microsoft connection.
 *
 * Three things must hold: an unknown connector type never reaches the network,
 * the authorization URL the API returns goes through the safe-navigation guard
 * (never straight to `window.location`), and a refusal reports the **server's**
 * reason — the message that tells the user their Google project is missing a
 * scope, rather than a generic "Failed to initiate OAuth".
 */

import { describe, it, expect, vi, beforeEach } from 'vitest';

import { renderHook, act } from '@/__tests__/test-utils';

const { get } = vi.hoisted(() => ({ get: vi.fn() }));
// Default client stubbed, `ApiError` real: the rejection shape is the contract.
vi.mock('@/lib/api-client', async importOriginal => ({
  ...(await importOriginal<typeof import('@/lib/api-client')>()),
  default: { get },
}));
const { navigateToAuthorizationUrl } = vi.hoisted(() => ({
  navigateToAuthorizationUrl: vi.fn(),
}));
vi.mock('@/lib/safe-navigation', () => ({ navigateToAuthorizationUrl }));
vi.mock('@/lib/logger', () => ({
  logger: { debug: vi.fn(), error: vi.fn(), warn: vi.fn(), info: vi.fn() },
}));

import { ApiError } from '@/lib/api-client';

import { useOAuthConnect } from '../useOAuthConnect';

const ENDPOINTS = { gmail: '/auth/google/gmail' };

function setup(onError = vi.fn()) {
  const view = renderHook(() => useOAuthConnect(ENDPOINTS, 'TestSection', { onError }));
  return { ...view, onError };
}

beforeEach(() => {
  vi.clearAllMocks();
  get.mockResolvedValue({ authorization_url: 'https://accounts.google.com/o/oauth2/auth?x=1' });
});

describe('useOAuthConnect', () => {
  it('hands the authorization URL to the navigation guard', async () => {
    const { result } = setup();
    await act(async () => {
      await result.current.connect('gmail');
    });

    expect(get).toHaveBeenCalledWith('/auth/google/gmail');
    expect(navigateToAuthorizationUrl).toHaveBeenCalledWith(
      'https://accounts.google.com/o/oauth2/auth?x=1',
      'oauth-gmail'
    );
  });

  it('refuses a connector type with no configured endpoint, without calling the API', async () => {
    const { result, onError } = setup();
    await act(async () => {
      await result.current.connect('unknown_provider');
    });

    expect(get).not.toHaveBeenCalled();
    expect(navigateToAuthorizationUrl).not.toHaveBeenCalled();
    expect(onError).toHaveBeenCalledWith(
      'No OAuth endpoint configured for connector: unknown_provider'
    );
  });

  it("reports the server's reason when the API refuses", async () => {
    get.mockRejectedValue(
      new ApiError('irrelevant', 503, { detail: 'Google OAuth client is not configured' })
    );
    const { result, onError } = setup();
    await act(async () => {
      await result.current.connect('gmail');
    });

    expect(onError).toHaveBeenCalledWith('Google OAuth client is not configured');
    expect(navigateToAuthorizationUrl).not.toHaveBeenCalled();
  });

  it('falls back to a generic message when the failure carries no detail', async () => {
    get.mockRejectedValue(new Error('Failed to fetch'));
    const { result, onError } = setup();
    await act(async () => {
      await result.current.connect('gmail');
    });

    expect(onError).toHaveBeenCalledWith('Failed to initiate OAuth');
  });

  it('reports a refused (unsafe) authorization URL rather than navigating', async () => {
    navigateToAuthorizationUrl.mockImplementation(() => {
      throw new Error('The authorization URL returned by the server is not a valid https address.');
    });
    const { result, onError } = setup();
    await act(async () => {
      await result.current.connect('gmail');
    });

    expect(onError).toHaveBeenCalledWith('Failed to initiate OAuth');
  });

  it('works without an onError callback', async () => {
    get.mockRejectedValue(new Error('down'));
    const { result } = renderHook(() => useOAuthConnect(ENDPOINTS, 'TestSection'));
    await act(async () => {
      await expect(result.current.connect('gmail')).resolves.toBeUndefined();
    });
  });
});
