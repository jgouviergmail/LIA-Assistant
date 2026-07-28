/**
 * RAG upload proxy — admission control and route-escape guard.
 *
 * SEC-017: `spaceId` is interpolated into the upstream URL. Before that fix, an
 * encoded value (`..%2f..%2fauth%2flogout`) survived WHATWG URL normalization
 * and could retarget a *different* backend POST route while carrying the
 * session cookie.
 *
 * SEC-006: the handler used to call `request.arrayBuffer()` before any
 * authentication or size check, so anonymous concurrent POSTs could exhaust the
 * frontend container's heap. Admission is now ordered — UUID → cookie present →
 * session valid upstream → concurrency slot → Content-Length → bounded read —
 * and nothing is buffered until all of them pass.
 *
 * FN-2: only the session cookie is forwarded upstream, never the whole `Cookie`
 * header.
 *
 * The transport is Node's `http`/`https` (a single one, so a failed attempt can
 * never replay an upload the backend already accepted), so these tests mock
 * `https.request` rather than `fetch`.
 */

import { NextRequest } from 'next/server';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { EventEmitter } from 'events';

const requestSpy = vi.fn();

vi.mock('https', () => ({
  default: {
    Agent: class {},
    request: (...args: unknown[]) => requestSpy(...args),
  },
}));
vi.mock('http', () => ({
  default: { request: (...args: unknown[]) => requestSpy(...args) },
}));

const { POST } = await import('./route');

const VALID_UUID = '3f1e8c9a-1b2c-4d5e-8f90-a1b2c3d4e5f6';

/** A fake `ClientRequest` that replays a canned upstream response. */
function fakeUpstream(status: number, body: string) {
  return (
    _options: unknown,
    callback: (
      res: EventEmitter & {
        statusCode: number;
        headers: Record<string, string>;
        destroy: () => void;
      }
    ) => void
  ) => {
    const req = Object.assign(new EventEmitter(), {
      setTimeout: vi.fn(),
      write: vi.fn(),
      end: vi.fn(() => {
        const res = Object.assign(new EventEmitter(), {
          statusCode: status,
          headers: { 'content-type': 'application/json' },
          destroy: vi.fn(),
        });
        queueMicrotask(() => {
          res.emit('data', Buffer.from(body));
          res.emit('end');
        });
        callback(res);
      }),
      destroy: vi.fn(),
    });
    return req;
  };
}

/** Route every upstream call (auth check + upload) to a 200 response. */
function stubUpstreamOk(uploadBody = '{"id":"doc-1"}') {
  requestSpy.mockImplementation((options: { path?: string }, cb: never) => {
    const path = options?.path ?? '';
    const body = path.includes('/auth/me') ? '{"id":"user-1"}' : uploadBody;
    return fakeUpstream(200, body)(options, cb);
  });
}

function makeRequest(
  body: BodyInit = 'multipart-body',
  headers: Record<string, string> = {}
): NextRequest {
  return new NextRequest('http://localhost/api/rag-upload/x', {
    method: 'POST',
    body,
    headers: {
      'content-type': 'multipart/form-data; boundary=x',
      cookie: 'lia_session=abc',
      ...headers,
    },
  });
}

function callPost(spaceId: string, request: NextRequest = makeRequest()) {
  return POST(request, { params: Promise.resolve({ spaceId }) });
}

beforeEach(() => {
  requestSpy.mockReset();
  stubUpstreamOk();
});

afterEach(() => {
  vi.restoreAllMocks();
});

describe('SEC-017 — spaceId route-escape guard', () => {
  const MALICIOUS_IDS = [
    '..',
    '../../auth/logout',
    '..%2f..%2fauth%2flogout',
    '..%252f..%252fauth', // double-encoded
    'a/b',
    'a\\b',
    'valid-looking-but-not-uuid',
    '',
    ' ',
    '00000000-0000-0000-0000-00000000000', // 11 trailing chars: too short
    '00000000-0000-0000-0000-0000000000000', // 13 trailing chars: too long
    'zzzzzzzz-0000-0000-0000-000000000000', // non-hex
    '00000000-0000-0000-0000-000000000000?x=1', // trailing query
  ];

  it.each(MALICIOUS_IDS)('rejects %j with 400 and makes no upstream request', async spaceId => {
    const res = await callPost(spaceId);

    expect(res.status).toBe(400);
    expect(requestSpy).not.toHaveBeenCalled();
  });

  it('proxies a valid UUID to the exact rag-spaces documents path', async () => {
    const res = await callPost(VALID_UUID);

    expect(res.status).toBe(200);
    const upload = requestSpy.mock.calls.find(([o]) => o.path?.includes('/documents'));
    expect(upload?.[0].path).toBe(`/api/v1/rag-spaces/${VALID_UUID}/documents`);
  });

  it('accepts a valid UUID case-insensitively', async () => {
    const res = await callPost(VALID_UUID.toUpperCase());
    expect(res.status).toBe(200);
  });
});

describe('SEC-006 — authentication before the body is read', () => {
  it('refuses without a session cookie and never contacts upstream', async () => {
    const request = new NextRequest('http://localhost/api/rag-upload/x', {
      method: 'POST',
      body: 'multipart-body',
      headers: { 'content-type': 'multipart/form-data; boundary=x' },
    });

    const res = await callPost(VALID_UUID, request);

    expect(res.status).toBe(401);
    expect(requestSpy).not.toHaveBeenCalled();
  });

  it('refuses a cookie that upstream does not recognise', async () => {
    // Cookie presence is not authentication — a forged value must not buy a
    // body read.
    requestSpy.mockImplementation(fakeUpstream(401, '{"detail":"nope"}'));

    const res = await callPost(VALID_UUID);

    expect(res.status).toBe(401);
    // Only the session check ran; the upload was never attempted.
    expect(requestSpy.mock.calls.every(([o]) => o.path?.includes('/auth/me'))).toBe(true);
  });

  it('fails closed when the session check cannot reach upstream', async () => {
    requestSpy.mockImplementation(() => {
      const req = Object.assign(new EventEmitter(), {
        setTimeout: vi.fn(),
        write: vi.fn(),
        end: vi.fn(() => queueMicrotask(() => req.emit('error', new Error('ECONNREFUSED')))),
        destroy: vi.fn(),
      });
      return req;
    });

    const res = await callPost(VALID_UUID);

    expect(res.status).toBe(401);
  });
});

describe('SEC-006 — size ceilings', () => {
  it('rejects an over-limit Content-Length before reading the body', async () => {
    const request = makeRequest('small-body', { 'content-length': String(64 * 1024 * 1024) });

    const res = await callPost(VALID_UUID, request);

    expect(res.status).toBe(413);
    // The session check ran; the upload did not.
    expect(requestSpy.mock.calls.every(([o]) => o.path?.includes('/auth/me'))).toBe(true);
  });

  it('rejects an oversized body that lies about its length', async () => {
    // 22 MB > the 21 MB ceiling, with no Content-Length to betray it: only the
    // streaming counter can catch this.
    const oversized = new Uint8Array(22 * 1024 * 1024);

    const res = await callPost(VALID_UUID, makeRequest(oversized));

    expect(res.status).toBe(413);
    expect(requestSpy.mock.calls.every(([o]) => o.path?.includes('/auth/me'))).toBe(true);
  });

  it('accepts a legitimate upload just under the ceiling', async () => {
    // Guards the fix against being a blanket refusal: a real 19 MB document
    // must still go through.
    const legitimate = new Uint8Array(19 * 1024 * 1024);

    const res = await callPost(VALID_UUID, makeRequest(legitimate));

    expect(res.status).toBe(200);
    expect(requestSpy.mock.calls.some(([o]) => o.path?.includes('/documents'))).toBe(true);
  });
});

describe('FN-2 — only the session cookie is forwarded', () => {
  it('drops unrelated cookies from the upstream request', async () => {
    const request = makeRequest('multipart-body', {
      cookie: 'lia_session=abc; analytics_id=track-me; feature_flags=beta',
    });

    await callPost(VALID_UUID, request);

    const upload = requestSpy.mock.calls.find(([o]) => o.path?.includes('/documents'));
    expect(upload?.[0].headers.cookie).toBe('lia_session=abc');
    expect(upload?.[0].headers.cookie).not.toContain('analytics_id');
    expect(upload?.[0].headers.cookie).not.toContain('feature_flags');
  });
});

describe('SEC-006 — error handling', () => {
  it('never leaks the transport error to the client', async () => {
    requestSpy.mockImplementation((options: { path?: string }, cb: never) => {
      if (options?.path?.includes('/auth/me')) {
        return fakeUpstream(200, '{"id":"user-1"}')(options, cb);
      }
      const req = Object.assign(new EventEmitter(), {
        setTimeout: vi.fn(),
        write: vi.fn(),
        end: vi.fn(() =>
          queueMicrotask(() =>
            req.emit('error', new Error('connect ECONNREFUSED 172.18.0.4:8000 selfsigned'))
          )
        ),
        destroy: vi.fn(),
      });
      return req;
    });

    const res = await callPost(VALID_UUID);
    const payload = await res.json();

    expect(res.status).toBe(502);
    expect(JSON.stringify(payload)).not.toContain('172.18.0.4');
    expect(JSON.stringify(payload)).not.toContain('ECONNREFUSED');
  });

  it('settles when upstream resets mid-response instead of hanging', async () => {
    // A reset after the headers emits 'error' on the RESPONSE, not the request.
    // Unhandled, the promise never settles and the upload keeps its concurrency
    // slot until the socket timeout — four of those and the route is wedged.
    requestSpy.mockImplementation((options: { path?: string }, cb: never) => {
      if (options?.path?.includes('/auth/me')) {
        return fakeUpstream(200, '{"id":"user-1"}')(options, cb);
      }
      const req = Object.assign(new EventEmitter(), {
        setTimeout: vi.fn(),
        write: vi.fn(),
        end: vi.fn(() => {
          const res = Object.assign(new EventEmitter(), {
            statusCode: 200,
            headers: { 'content-type': 'application/json' },
            destroy: vi.fn(),
          });
          queueMicrotask(() => {
            res.emit('data', Buffer.from('{"partial'));
            res.emit('error', new Error('ECONNRESET'));
          });
          (cb as unknown as (r: typeof res) => void)(res);
        }),
        destroy: vi.fn(),
      });
      return req;
    });

    const res = await callPost(VALID_UUID);

    expect(res.status).toBe(502);
  });

  it('surfaces the upstream status so the UI can show its message', async () => {
    requestSpy.mockImplementation((options: { path?: string }, cb: never) => {
      const body = options?.path?.includes('/auth/me')
        ? '{"id":"user-1"}'
        : '{"detail":"Unsupported file type"}';
      const status = options?.path?.includes('/auth/me') ? 200 : 415;
      return fakeUpstream(status, body)(options, cb);
    });

    const res = await callPost(VALID_UUID);

    expect(res.status).toBe(415);
    expect((await res.json()).detail).toBe('Unsupported file type');
  });
});
