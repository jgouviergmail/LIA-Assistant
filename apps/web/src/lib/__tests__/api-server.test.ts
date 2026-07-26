/**
 * The Server-Action HTTP client (BFF, server side).
 *
 * A Server Action runs in an isolated Node context: no automatic cookie jar,
 * no relative URLs. This client is the only thing that turns the request's
 * HTTP-only session cookie into an authenticated backend call, so its contract
 * is a security contract — forward the cookie, keep the timeout, and hand the
 * backend's own error detail back to the action.
 *
 * Everything here drives the real module over a stubbed `fetch`; `next/headers`
 * is the single boundary replaced, because it only exists inside a request.
 */

import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';

import { SERVER_ACTION_TIMEOUT } from '@/lib/constants';

const { cookieGet } = vi.hoisted(() => ({ cookieGet: vi.fn() }));
vi.mock('next/headers', () => ({
  cookies: async () => ({ get: cookieGet }),
}));

import {
  createServerApiClient,
  ServerApiError,
  isServerContext,
  getApiUrl,
} from '@/lib/api-server';

/** A JSON response the way the backend actually answers. */
function jsonResponse(status: number, body: unknown): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'content-type': 'application/json' },
  });
}

/** Last `fetch` call, as [url, init]. */
function lastCall(): [string, RequestInit] {
  const mock = globalThis.fetch as unknown as ReturnType<typeof vi.fn>;
  const call = mock.mock.calls.at(-1);
  return [call![0] as string, call![1] as RequestInit];
}

function headersOf(init: RequestInit): Record<string, string> {
  return (init.headers ?? {}) as Record<string, string>;
}

const ORIGINAL_FETCH = globalThis.fetch;
const ORIGINAL_API_URL_SERVER = process.env.API_URL_SERVER;

beforeEach(() => {
  vi.clearAllMocks();
  // The client reports 5xx/401/403 on the console by design; the failure cases
  // below exercise that path, and the noise would drown the run.
  vi.spyOn(console, 'error').mockImplementation(() => {});
  cookieGet.mockReturnValue({ name: 'lia_session', value: 'sess-42' });
  // A fresh Response per call: a body can only be read once.
  globalThis.fetch = vi.fn().mockImplementation(async () => jsonResponse(200, { ok: true }));
  process.env.API_URL_SERVER = 'http://api:8000';
});

afterEach(() => {
  vi.restoreAllMocks();
  globalThis.fetch = ORIGINAL_FETCH;
  if (ORIGINAL_API_URL_SERVER === undefined) {
    delete process.env.API_URL_SERVER;
  } else {
    process.env.API_URL_SERVER = ORIGINAL_API_URL_SERVER;
  }
});

describe('createServerApiClient — authentication forwarding', () => {
  it('forwards the session cookie the request carried', async () => {
    const api = await createServerApiClient();
    await api.get('/users/me');

    const [url, init] = lastCall();
    expect(url).toBe('http://api:8000/api/v1/users/me');
    expect(headersOf(init).Cookie).toBe('lia_session=sess-42');
  });

  it('sends no Cookie header when the caller has no session', async () => {
    cookieGet.mockReturnValue(undefined);
    const api = await createServerApiClient();
    await api.get('/users/me');

    expect(headersOf(lastCall()[1])).not.toHaveProperty('Cookie');
  });

  it('reads the cookie once, at creation — not per request', async () => {
    const api = await createServerApiClient();
    await api.get('/a');
    await api.get('/b');

    expect(cookieGet).toHaveBeenCalledTimes(1);
  });

  it('falls back to the Docker service name when API_URL_SERVER is unset', async () => {
    delete process.env.API_URL_SERVER;
    const api = await createServerApiClient();
    await api.get('/ping');

    expect(lastCall()[0]).toBe('http://api:8000/api/v1/ping');
  });
});

describe('createServerApiClient — request shaping', () => {
  it('serialises the body and declares JSON on POST', async () => {
    const api = await createServerApiClient();
    await api.post('/admin/llm/pricing', { model_name: 'gpt-x' });

    const [, init] = lastCall();
    expect(init.method).toBe('POST');
    expect(init.body).toBe('{"model_name":"gpt-x"}');
    expect(headersOf(init)['Content-Type']).toBe('application/json');
  });

  it.each([
    ['put', 'PUT'],
    ['patch', 'PATCH'],
  ] as const)('sends %s as %s with a serialised body', async (methodName, verb) => {
    const api = await createServerApiClient();
    await api[methodName]('/x', { a: 1 });

    const [, init] = lastCall();
    expect(init.method).toBe(verb);
    expect(init.body).toBe('{"a":1}');
  });

  it('omits the body entirely when a mutation has no payload', async () => {
    const api = await createServerApiClient();
    await api.post('/admin/llm/pricing/reload-cache');

    expect(lastCall()[1].body).toBeUndefined();
  });

  it('appends query parameters', async () => {
    const api = await createServerApiClient();
    await api.get('/users', { params: { page: 2, q: 'a b', active: true } });

    expect(lastCall()[0]).toBe('http://api:8000/api/v1/users?page=2&q=a+b&active=true');
  });

  it('sends DELETE with the caller-supplied body', async () => {
    const api = await createServerApiClient();
    await api.delete('/users/admin/u1/delete-account', {
      body: JSON.stringify({ reason: 'spam' }),
    });

    const [, init] = lastCall();
    expect(init.method).toBe('DELETE');
    expect(init.body).toBe('{"reason":"spam"}');
    // The regression this pins: a caller-supplied option must never wipe the
    // headers built by the client — the session cookie lives there.
    expect(headersOf(init).Cookie).toBe('lia_session=sess-42');
  });

  it('keeps the session cookie when the caller supplies its own headers', async () => {
    const api = await createServerApiClient();
    await api.get('/export', { headers: { Accept: 'text/csv' } });

    const headers = headersOf(lastCall()[1]);
    expect(headers.Accept).toBe('text/csv');
    expect(headers.Cookie).toBe('lia_session=sess-42');
    expect(headers['Content-Type']).toBe('application/json');
  });

  it('combines its timeout with a caller-supplied cancellation', async () => {
    const api = await createServerApiClient();
    const caller = new AbortController();
    await api.get('/slow', { signal: caller.signal });

    const combined = lastCall()[1].signal as AbortSignal;
    // Neither signal is dropped: the caller can still cancel, and the client
    // keeps the timeout it promises.
    expect(combined).not.toBe(caller.signal);
    expect(combined.aborted).toBe(false);

    caller.abort();
    expect(combined.aborted).toBe(true);
  });
});

describe('createServerApiClient — responses', () => {
  it('returns the parsed JSON body', async () => {
    (globalThis.fetch as ReturnType<typeof vi.fn>).mockResolvedValue(
      jsonResponse(200, { templates: [{ template_model_name: 'o3' }] })
    );
    const api = await createServerApiClient();

    await expect(api.get('/admin/llm/reasoning-templates')).resolves.toEqual({
      templates: [{ template_model_name: 'o3' }],
    });
  });

  it('returns undefined on 204 No Content', async () => {
    (globalThis.fetch as ReturnType<typeof vi.fn>).mockResolvedValue(
      new Response(null, { status: 204 })
    );
    const api = await createServerApiClient();

    await expect(api.delete('/admin/llm/pricing/p1')).resolves.toBeUndefined();
  });

  it('returns undefined on a 200 with an empty body', async () => {
    (globalThis.fetch as ReturnType<typeof vi.fn>).mockResolvedValue(
      new Response('', { status: 200 })
    );
    const api = await createServerApiClient();

    await expect(api.post('/admin/llm/pricing/reload-cache')).resolves.toBeUndefined();
  });

  it('returns raw text when the response is not JSON', async () => {
    (globalThis.fetch as ReturnType<typeof vi.fn>).mockResolvedValue(
      new Response('pong', { status: 200, headers: { 'content-type': 'text/plain' } })
    );
    const api = await createServerApiClient();

    await expect(api.get('/ping')).resolves.toBe('pong');
  });
});

describe('createServerApiClient — failures', () => {
  it("raises ServerApiError carrying the backend's detail", async () => {
    (globalThis.fetch as ReturnType<typeof vi.fn>).mockResolvedValue(
      jsonResponse(409, { detail: 'Model already exists' })
    );
    const api = await createServerApiClient();

    const error = await api.post('/admin/llm/pricing', {}).catch((e: unknown) => e);
    expect(error).toBeInstanceOf(ServerApiError);
    expect((error as ServerApiError).status).toBe(409);
    expect((error as ServerApiError).message).toBe('Model already exists');
    expect((error as ServerApiError).data).toEqual({ detail: 'Model already exists' });
  });

  it('falls back to the status line when the error body says nothing', async () => {
    (globalThis.fetch as ReturnType<typeof vi.fn>).mockResolvedValue(jsonResponse(500, {}));
    const api = await createServerApiClient();

    await expect(api.get('/boom')).rejects.toMatchObject({ message: 'HTTP 500', status: 500 });
  });

  it('wraps a network failure as a status-0 ServerApiError', async () => {
    (globalThis.fetch as ReturnType<typeof vi.fn>).mockRejectedValue(new TypeError('fetch failed'));
    const api = await createServerApiClient();

    const error = await api.get('/x').catch((e: unknown) => e);
    expect(error).toBeInstanceOf(ServerApiError);
    expect((error as ServerApiError).status).toBe(0);
    expect((error as ServerApiError).message).toBe('fetch failed');
  });

  it('aborts the request once the server-action timeout elapses', async () => {
    vi.useFakeTimers();
    try {
      let observed!: AbortSignal;
      (globalThis.fetch as ReturnType<typeof vi.fn>).mockImplementation(
        (_url: string, init: RequestInit) =>
          new Promise((_resolve, reject) => {
            observed = init.signal as AbortSignal;
            observed.addEventListener('abort', () => reject(new Error('aborted')));
          })
      );
      const api = await createServerApiClient();
      const pending = api.get('/slow').catch((e: unknown) => e);

      expect(observed.aborted).toBe(false);
      await vi.advanceTimersByTimeAsync(SERVER_ACTION_TIMEOUT + 1);

      expect(observed.aborted).toBe(true);
      await expect(pending).resolves.toBeInstanceOf(ServerApiError);
    } finally {
      vi.useRealTimers();
    }
  });
});

describe('context helpers', () => {
  it('reports the server context when there is no window', () => {
    const hadWindow = 'window' in globalThis;
    // jsdom provides a window, so this asserts the browser branch instead.
    expect(isServerContext()).toBe(!hadWindow);
  });

  it('returns the browser API URL when a window exists', () => {
    expect(getApiUrl()).toBe(process.env.NEXT_PUBLIC_API_URL || '');
  });
});
