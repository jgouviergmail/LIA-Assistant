/**
 * The one thing a native shell tells its server about itself.
 *
 * An OAuth flow started in the app has to come back to the app, and the
 * callback learns that from the state the authorize call wrote. The authorize
 * call is an ordinary API request, so the fact has to travel on it.
 *
 * A custom header forces a CORS preflight, which is exactly why the browser
 * path is asserted here as hard as the shell path: a browser must send nothing
 * new and pay nothing. In a shell the cost is one OPTIONS per method and path
 * every ten minutes — the API's `max_age` — and it buys the alternative's
 * absence: a list of OAuth paths in this file, which would rot the first time
 * someone adds a connector.
 */

import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';

const { isNativeShell } = vi.hoisted(() => ({ isNativeShell: vi.fn(() => false) }));
vi.mock('@/lib/native/shell', () => ({ isNativeShell, openInSystemBrowser: vi.fn() }));

import apiClient from '@/lib/api-client';

function headersOf(call: unknown): Record<string, string> {
  const init = (call as [string, RequestInit])[1];
  return (init.headers ?? {}) as Record<string, string>;
}

beforeEach(() => {
  vi.restoreAllMocks();
  isNativeShell.mockReturnValue(false);
  vi.spyOn(globalThis, 'fetch').mockResolvedValue(
    new Response(JSON.stringify({ ok: true }), {
      status: 200,
      headers: { 'content-type': 'application/json' },
    })
  );
});

afterEach(() => {
  vi.restoreAllMocks();
});

describe('in a browser', () => {
  it('sends no extra header at all', async () => {
    await apiClient.get('/connectors');

    // Every custom header is a preflight the web app would pay for on every
    // request. Nothing here is worth that.
    const headers = headersOf(vi.mocked(globalThis.fetch).mock.calls[0]);
    expect(Object.keys(headers)).not.toContain('X-LIA-Native');
  });
});

describe('in a native shell', () => {
  beforeEach(() => {
    isNativeShell.mockReturnValue(true);
  });

  it('declares itself so an OAuth flow can find its way home', async () => {
    await apiClient.get('/connectors/gmail/authorize');

    expect(headersOf(vi.mocked(globalThis.fetch).mock.calls[0])['X-LIA-Native']).toBe('1');
  });

  it('declares itself on every method, not only the one flow that needs it', async () => {
    await apiClient.post('/connectors/gmail/authorize', {});

    // Scoping this to a list of OAuth paths would be one more place to
    // remember when a connector is added — and forgetting it strands that
    // connector's users in a browser, silently.
    expect(headersOf(vi.mocked(globalThis.fetch).mock.calls[0])['X-LIA-Native']).toBe('1');
  });

  it('does not disturb the headers the client already computes', async () => {
    await apiClient.post('/connectors/gmail/authorize', { a: 1 });

    const headers = headersOf(vi.mocked(globalThis.fetch).mock.calls[0]);
    expect(headers['Content-Type']).toBe('application/json');
    expect(headers['X-LIA-Native']).toBe('1');
  });

  it('still sends the session cookie', async () => {
    await apiClient.get('/connectors');

    // The BFF contract is what makes the shells possible at all; a header must
    // not be added in a way that rebuilds the request options.
    const init = vi.mocked(globalThis.fetch).mock.calls[0][1] as RequestInit;
    expect(init.credentials).toBe('include');
  });
});
