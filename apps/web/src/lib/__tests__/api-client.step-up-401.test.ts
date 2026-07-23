/**
 * Step-up 401 contract — non-regression.
 *
 * A 401 from a step-up verification endpoint means "wrong password/code",
 * not "session expired": the StepUpDialog shows an inline error and lets
 * the user retry. The api-client's global 401 handler used to hard-redirect
 * these to /login, ejecting the user from an open settings flow on a simple
 * typo (found live, 2026-07-23). This pins the exemption.
 */

import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import apiClient, { ApiError, isCredentialCheckUrl } from '../api-client';

function response401(url: string): Response {
  const res = new Response(JSON.stringify({ detail: 'Invalid credentials' }), {
    status: 401,
    headers: { 'content-type': 'application/json' },
  });
  Object.defineProperty(res, 'url', { value: url });
  return res;
}

describe('isCredentialCheckUrl', () => {
  it.each([
    'https://api.example.dev/api/v1/auth/step-up/password',
    'https://api.example.dev/api/v1/auth/step-up/totp',
    'https://api.example.dev/api/v1/auth/step-up/webauthn/verify',
  ])('marks step-up verification endpoint %s', url => {
    expect(isCredentialCheckUrl(url)).toBe(true);
  });

  it.each([
    'https://api.example.dev/api/v1/auth/me',
    'https://api.example.dev/api/v1/auth/login',
    'https://api.example.dev/api/v1/conversations',
  ])('leaves session-authenticated endpoint %s to the eject handler', url => {
    expect(isCredentialCheckUrl(url)).toBe(false);
  });
});

describe('401 handling by endpoint class', () => {
  const originalLocation = window.location;

  beforeEach(() => {
    // The eject handler assigns window.location.href — observe it.
    Object.defineProperty(window, 'location', {
      writable: true,
      value: { ...originalLocation, pathname: '/fr/dashboard/settings', href: '' },
    });
  });

  afterEach(() => {
    Object.defineProperty(window, 'location', {
      writable: true,
      value: originalLocation,
    });
    vi.restoreAllMocks();
  });

  it('step-up 401 throws inline without redirecting to login', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(
      response401('https://api.example.dev/api/v1/auth/step-up/password')
    );

    await expect(apiClient.post('/auth/step-up/password', { password: 'typo' })).rejects.toEqual(
      expect.objectContaining({ status: 401, name: 'ApiError' })
    );
    expect(window.location.href).toBe('');
  });

  it('session 401 on a protected page still ejects to the localized login', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(
      response401('https://api.example.dev/api/v1/auth/me')
    );

    await expect(apiClient.get('/auth/me')).rejects.toBeInstanceOf(ApiError);
    expect(window.location.href).toBe('/fr/login');
  });
});
