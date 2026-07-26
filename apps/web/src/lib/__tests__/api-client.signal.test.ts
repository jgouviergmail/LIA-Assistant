/**
 * `apiClient` request options — what a caller can influence, and what it cannot.
 *
 * The option object is spread FIRST so a caller cannot accidentally drop the
 * cookie, the computed Content-Type or the timeout. Cancellation is the one
 * thing that must survive that rule: a debounced search or an unmounting
 * component has to be able to stop a request it no longer needs, so the two
 * signals are combined rather than ranked.
 */

import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';

import apiClient from '@/lib/api-client';

const ORIGINAL_FETCH = globalThis.fetch;

function lastInit(): RequestInit {
  const mock = globalThis.fetch as unknown as ReturnType<typeof vi.fn>;
  return mock.mock.calls.at(-1)![1] as RequestInit;
}

beforeEach(() => {
  vi.clearAllMocks();
  globalThis.fetch = vi
    .fn()
    .mockImplementation(
      async () =>
        new Response('{}', { status: 200, headers: { 'content-type': 'application/json' } })
    );
});

afterEach(() => {
  globalThis.fetch = ORIGINAL_FETCH;
});

describe('apiClient — cancellation', () => {
  it('arms a signal even when the caller passes none', async () => {
    await apiClient.get('/x');

    expect(lastInit().signal).toBeInstanceOf(AbortSignal);
    expect((lastInit().signal as AbortSignal).aborted).toBe(false);
  });

  it("honours the caller's abort without dropping the timeout", async () => {
    const caller = new AbortController();

    await apiClient.get('/x', { signal: caller.signal });
    const combined = lastInit().signal as AbortSignal;

    expect(combined).not.toBe(caller.signal);
    expect(combined.aborted).toBe(false);

    caller.abort();
    expect(combined.aborted).toBe(true);
  });

  it('an already-aborted caller signal aborts the combined one immediately', async () => {
    await apiClient.get('/x', { signal: AbortSignal.abort() });

    expect((lastInit().signal as AbortSignal).aborted).toBe(true);
  });
});

describe('apiClient — an error is an error, body or not', () => {
  function respondWith(status: number, body: string | null, contentType?: string): void {
    (globalThis.fetch as ReturnType<typeof vi.fn>).mockImplementation(
      async () =>
        new Response(body, {
          status,
          headers: contentType ? { 'content-type': contentType } : undefined,
        })
    );
  }

  it.each([500, 502, 503])('a %i with an EMPTY body still rejects', async status => {
    // The empty-body early return used to run BEFORE the status check, so a
    // bare 5xx — what a load balancer returns when the upstream is down —
    // resolved with `undefined`. The caller then read a field off it and
    // crashed somewhere unrelated, or displayed "no data" for an outage.
    respondWith(status, null);

    await expect(apiClient.get('/x')).rejects.toMatchObject({ status });
  });

  it('a 4xx with an empty body rejects too', async () => {
    respondWith(422, '');

    await expect(apiClient.get('/x')).rejects.toMatchObject({ status: 422 });
  });

  it('a 204 still resolves with nothing — that one IS a success', async () => {
    respondWith(204, null);

    await expect(apiClient.get('/x')).resolves.toBeUndefined();
  });

  it('a 200 with an empty body still resolves with nothing', async () => {
    respondWith(200, '');

    await expect(apiClient.get('/x')).resolves.toBeUndefined();
  });

  it('an error body that is not JSON is kept as text on the error', async () => {
    respondWith(502, '<html>Bad Gateway</html>', 'text/html');

    const error = await apiClient.get('/x').catch((e: unknown) => e);
    expect((error as { status: number }).status).toBe(502);
    expect((error as { data: unknown }).data).toBe('<html>Bad Gateway</html>');
  });
});

describe('apiClient — options a caller must not be able to break', () => {
  it('keeps the BFF cookie even when the caller passes credentials', async () => {
    await apiClient.get('/x', { credentials: 'omit' });

    expect(lastInit().credentials).toBe('include');
  });

  it('keeps the computed Content-Type while merging caller headers', async () => {
    await apiClient.post('/x', { a: 1 }, { headers: { Accept: 'text/csv' } });

    const headers = lastInit().headers as Record<string, string>;
    expect(headers['Content-Type']).toBe('application/json');
    expect(headers.Accept).toBe('text/csv');
  });

  it('does not declare a JSON body on a GET', async () => {
    // A Content-Type on a simple GET forces a CORS preflight for nothing.
    await apiClient.get('/x');

    expect(lastInit().headers as Record<string, string>).not.toHaveProperty('Content-Type');
  });

  it('keeps the verb the method implies, whatever the caller passed', async () => {
    await apiClient.get('/x', { method: 'DELETE' });

    expect(lastInit().method).toBe('GET');
  });
});
