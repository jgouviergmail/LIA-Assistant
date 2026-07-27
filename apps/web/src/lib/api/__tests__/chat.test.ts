/**
 * ChatSSEClient and the small run-control endpoints around it.
 *
 * This is the transport the whole conversation rides on, so the tests drive the
 * **real** client over a stubbed `fetch` returning genuine `Response` objects
 * (streams included): URL building, credential mode, status→i18n mapping,
 * frame parsing and cancellation are all exercised for real rather than mocked
 * away.
 *
 * Two properties matter more than the rest and are pinned explicitly:
 *  - **cancellation is silent and total** — aborting reports no error, and the
 *    chunks already buffered are dropped instead of leaking into the next run;
 *  - **a frame split across two network chunks is reassembled**, which is what
 *    happens the moment an answer is longer than a TCP segment.
 */

import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';

import type { ChatRequest, ChatStreamChunk } from '@/types/chat';

vi.mock('@/lib/logger', () => ({
  logger: { debug: vi.fn(), info: vi.fn(), warn: vi.fn(), error: vi.fn() },
}));

import {
  ChatSSEClient,
  ChatStreamError,
  cancelActiveRun,
  fetchActiveRun,
  fetchPendingHitl,
} from '../chat';
import { CHAT_SSE_STALL_TIMEOUT_MS } from '@/lib/constants';

const fetchMock = vi.fn();

/** A streaming response whose frames are delivered as separate network chunks. */
function sseResponse(chunks: string[], init: ResponseInit = {}): Response {
  const encoder = new TextEncoder();
  const stream = new ReadableStream({
    start(controller) {
      for (const chunk of chunks) controller.enqueue(encoder.encode(chunk));
      controller.close();
    },
  });
  return new Response(stream, { status: 200, ...init });
}

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json' },
  });
}

const REQUEST: ChatRequest = { message: 'bonjour', user_id: 'u-1', session_id: 's-1' };

/** Runs a full stream and reports everything the client called back with. */
async function runStream(response: Response | Error) {
  const client = new ChatSSEClient();
  const chunks: ChatStreamChunk[] = [];
  const errors: Error[] = [];
  let done = false;

  fetchMock.mockImplementation(() =>
    response instanceof Error ? Promise.reject(response) : Promise.resolve(response)
  );

  await client.streamChat(
    REQUEST,
    c => chunks.push(c),
    e => errors.push(e),
    () => {
      done = true;
    }
  );

  return { client, chunks, errors, done };
}

/** The i18n-ready error the client produced, as a plain object. */
function errorShape(error: Error) {
  const streamError = error instanceof ChatStreamError ? error : null;
  return {
    name: error.name,
    i18nKey: streamError?.i18nKey,
    i18nParams: streamError?.i18nParams,
    activeStreamId: streamError?.activeStreamId,
  };
}

beforeEach(() => {
  vi.clearAllMocks();
  vi.stubGlobal('fetch', fetchMock);
});

afterEach(() => {
  vi.unstubAllGlobals();
  vi.useRealTimers();
});

describe('ChatSSEClient — request shape', () => {
  it('posts the request to the stream endpoint with the session cookie', async () => {
    await runStream(sseResponse([]));

    const [url, init] = fetchMock.mock.calls[0];
    expect(String(url)).toMatch(/\/api\/v1\/agents\/chat\/stream$/);
    expect(init).toMatchObject({ method: 'POST', credentials: 'include' });
    expect(JSON.parse(String(init.body))).toEqual(REQUEST);
    expect(init.signal).toBeInstanceOf(AbortSignal);
  });
});

describe('ChatSSEClient — HTTP status mapping', () => {
  it.each([
    [403, 'AccountInactiveError', 'errors.chat.account_inactive'],
    [429, 'UsageLimitExceededError', 'errors.chat.usage_limit_exceeded'],
    [503, 'ServiceUnavailableError', 'errors.chat.service_unavailable'],
  ])('turns %s into %s', async (status, name, i18nKey) => {
    const { errors, done } = await runStream(new Response(null, { status }));

    expect(errors).toHaveLength(1);
    expect(errorShape(errors[0])).toMatchObject({ name, i18nKey });
    expect(done).toBe(false);
  });

  it('carries the status of a server error for the message', async () => {
    const { errors } = await runStream(new Response(null, { status: 502 }));

    expect(errorShape(errors[0])).toMatchObject({
      name: 'ServerError',
      i18nKey: 'errors.chat.server_error',
      i18nParams: { status: 502 },
    });
  });

  it('falls back to a generic HTTP error for other client statuses', async () => {
    const { errors } = await runStream(new Response(null, { status: 418, statusText: 'Teapot' }));

    expect(errorShape(errors[0])).toMatchObject({
      name: 'HttpError',
      i18nKey: 'errors.chat.http_error',
      i18nParams: { status: 418, statusText: 'Teapot' },
    });
  });

  it('surfaces the in-flight run id on a conflict, so the caller can reattach', async () => {
    const { errors } = await runStream(
      jsonResponse({ detail: { active_run: { stream_id: 'stream-7' } } }, 409)
    );

    expect(errorShape(errors[0])).toMatchObject({
      name: 'RunInProgressError',
      i18nKey: 'errors.chat.run_in_progress',
      activeStreamId: 'stream-7',
    });
  });

  it('still reports the conflict when its body is unreadable', async () => {
    const { errors } = await runStream(new Response('not json', { status: 409 }));

    expect(errorShape(errors[0])).toMatchObject({ name: 'RunInProgressError' });
    expect(errors[0]).toBeInstanceOf(ChatStreamError);
    expect((errors[0] as ChatStreamError).activeStreamId).toBeUndefined();
  });

  it('sends the user back to the login page after an expired session', async () => {
    vi.useFakeTimers();
    const original = window.location;
    Object.defineProperty(window, 'location', {
      value: { href: '', pathname: '/fr/dashboard/chat' },
      writable: true,
      configurable: true,
    });

    const { errors } = await runStream(new Response(null, { status: 401 }));
    expect(errorShape(errors[0])).toMatchObject({
      name: 'AuthenticationError',
      i18nKey: 'errors.chat.session_expired',
    });

    // The redirect is deferred so the user can read the message first.
    expect(window.location.href).toBe('');
    vi.advanceTimersByTime(2_000);
    expect(window.location.href).toBe('/login?redirect=%2Ffr%2Fdashboard%2Fchat');

    Object.defineProperty(window, 'location', { value: original, configurable: true });
  });

  it('reports a body-less success as a plain error', async () => {
    const { errors } = await runStream(new Response(null, { status: 200 }));

    expect(errors[0].message).toBe('Response body is null');
  });
});

describe('ChatSSEClient — transport failures', () => {
  it('maps a failed fetch to a network error', async () => {
    const { errors } = await runStream(new TypeError('Failed to fetch'));

    expect(errorShape(errors[0])).toMatchObject({
      name: 'NetworkError',
      i18nKey: 'errors.chat.network_error',
    });
  });

  it('wraps a non-Error rejection rather than losing it', async () => {
    const client = new ChatSSEClient();
    const errors: Error[] = [];
    fetchMock.mockRejectedValue('kaboom');

    await client.streamChat(
      REQUEST,
      () => {},
      e => errors.push(e),
      () => {}
    );

    expect(errorShape(errors[0])).toMatchObject({
      name: 'UnknownError',
      i18nKey: 'errors.chat.unknown_error',
    });
  });
});

describe('ChatSSEClient — frame parsing', () => {
  it('delivers the chunks in order and closes the stream', async () => {
    const { chunks, done, client } = await runStream(
      sseResponse([
        'data: {"type":"token","content":"Bon"}\n',
        'data: {"type":"token","content":"jour"}\n',
        'data: {"type":"done"}\n',
      ])
    );

    expect(chunks.map(c => c.type)).toEqual(['token', 'token', 'done']);
    expect(chunks[0]).toMatchObject({ content: 'Bon' });
    expect(done).toBe(true);
    expect(client.getIsConnected()).toBe(false);
  });

  it('reassembles a frame split across two network chunks', async () => {
    const { chunks } = await runStream(
      sseResponse(['data: {"type":"token","cont', 'ent":"complet"}\n'])
    );

    expect(chunks).toHaveLength(1);
    expect(chunks[0]).toMatchObject({ type: 'token', content: 'complet' });
  });

  it('ignores heartbeats and retry hints', async () => {
    const { chunks, done } = await runStream(
      sseResponse([': heartbeat\n', 'retry: 3000\n', 'data: {"type":"token"}\n'])
    );

    expect(chunks).toHaveLength(1);
    expect(done).toBe(true);
  });

  it('skips a malformed frame without dropping the ones after it', async () => {
    const { chunks, errors, done } = await runStream(
      sseResponse(['data: {oops\n', 'data: {"type":"done"}\n'])
    );

    expect(chunks.map(c => c.type)).toEqual(['done']);
    expect(errors).toHaveLength(0);
    expect(done).toBe(true);
  });

  it('logs an error chunk without turning it into a transport error', async () => {
    const { chunks, errors } = await runStream(
      sseResponse(['data: {"type":"error","error":"boom","error_code":"E1"}\n'])
    );

    // Error *chunks* are content, not transport failures: the consumer decides.
    expect(chunks[0]).toMatchObject({ type: 'error', error: 'boom' });
    expect(errors).toHaveLength(0);
  });
});

describe('ChatSSEClient — cancellation', () => {
  it('stays silent when the user aborts the stream', async () => {
    const client = new ChatSSEClient();
    const errors: Error[] = [];
    fetchMock.mockImplementation(
      (_url: string, init: RequestInit) =>
        new Promise((_resolve, reject) => {
          init.signal?.addEventListener('abort', () =>
            reject(new DOMException('Aborted', 'AbortError'))
          );
        })
    );

    const streaming = client.streamChat(
      REQUEST,
      () => {},
      e => errors.push(e),
      () => {}
    );
    client.cancel();
    await streaming;

    expect(errors).toHaveLength(0);
    expect(client.getIsConnected()).toBe(false);
  });

  it('drops the chunks that were already buffered when it was cancelled', async () => {
    const client = new ChatSSEClient();
    const chunks: ChatStreamChunk[] = [];
    const encoder = new TextEncoder();

    // Three frames arrive in ONE network chunk: they are all parsed in the
    // same loop, so the guard has to hold between them — cancelling on the
    // first must silence the two that are already in the buffer.
    const stream = new ReadableStream({
      start(controller) {
        controller.enqueue(
          encoder.encode(
            'data: {"type":"token","content":"avant"}\n' +
              'data: {"type":"token","content":"apres-1"}\n' +
              'data: {"type":"token","content":"apres-2"}\n'
          )
        );
        controller.close();
      },
    });
    fetchMock.mockResolvedValue(new Response(stream, { status: 200 }));

    client.cancel(); // no active controller yet — must not throw
    await client.streamChat(
      REQUEST,
      c => {
        chunks.push(c);
        client.cancel();
      },
      () => {},
      () => {}
    );

    expect(chunks.map(c => c.content)).toEqual(['avant']);
  });
});

describe('ChatSSEClient — reattaching to a background run', () => {
  async function reattach(response: Response) {
    const client = new ChatSSEClient();
    const chunks: ChatStreamChunk[] = [];
    const errors: Error[] = [];
    let replayEnded = 0;
    let done = false;
    fetchMock.mockResolvedValue(response);

    await client.reattachStream(
      'stream 7/8',
      c => chunks.push(c),
      e => errors.push(e),
      () => {
        done = true;
      },
      () => {
        replayEnded += 1;
      }
    );

    return { chunks, errors, replayEnded, done };
  }

  it('reads the run stream by its encoded id', async () => {
    await reattach(sseResponse([]));

    const [url, init] = fetchMock.mock.calls[0];
    expect(String(url)).toContain('/agents/runs/stream%207%2F8/stream');
    expect(init).toMatchObject({ method: 'GET', credentials: 'include' });
  });

  it('marks the boundary between the replay and the live tail', async () => {
    const { chunks, replayEnded, done } = await reattach(
      sseResponse([
        'data: {"type":"token","content":"rejoué"}\n',
        ': replay-end\n',
        'data: {"type":"token","content":"live"}\n',
      ])
    );

    expect(replayEnded).toBe(1);
    expect(chunks).toHaveLength(2);
    expect(done).toBe(true);
  });

  it('reports a run that is already gone', async () => {
    const { errors } = await reattach(new Response(null, { status: 404 }));

    expect(errorShape(errors[0])).toMatchObject({
      name: 'RunGoneError',
      i18nKey: 'errors.chat.run_gone',
      i18nParams: { status: 404 },
    });
  });

  it('reports an expired session while reattaching', async () => {
    const { errors } = await reattach(new Response(null, { status: 401 }));

    expect(errorShape(errors[0])).toMatchObject({ name: 'AuthenticationError' });
  });
});

describe('ChatSSEClient — stalled stream watchdog', () => {
  /**
   * A response whose body never yields and never closes: exactly what a mobile
   * browser leaves behind when the OS freezes a backgrounded tab. `read()`
   * neither resolves nor rejects, so without a watchdog the client sits in
   * `status: 'streaming'` forever — `isTyping` stays true, and the visibility
   * handler that would have called `checkAndResumeActiveRun()` returns early on
   * that very flag. Production 2026-07-27: four runs completed server-side
   * (`sse_stream_completed`) while the phone still displayed "Génération de la
   * réponse…", and not one `/runs/active` call was ever made.
   */
  function silentResponse(): Response {
    const stream = new ReadableStream({
      start() {
        /* deliberately silent: no enqueue, no close, no error */
      },
    });
    return new Response(stream, { status: 200 });
  }

  beforeEach(() => {
    vi.useFakeTimers();
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it('gives up on a silent stream instead of hanging forever', async () => {
    const client = new ChatSSEClient();
    const errors: Error[] = [];
    let done = false;
    fetchMock.mockResolvedValue(silentResponse());

    const streaming = client.streamChat(
      REQUEST,
      () => {},
      e => errors.push(e),
      () => {
        done = true;
      }
    );

    await vi.advanceTimersByTimeAsync(CHAT_SSE_STALL_TIMEOUT_MS + 1_000);
    await streaming;

    expect(errors).toHaveLength(1);
    expect(errorShape(errors[0])).toMatchObject({
      name: 'StreamStalledError',
      i18nKey: 'errors.chat.stream_stalled',
    });
    expect(done).toBe(false);
  });

  it('does not fire while the server keeps sending heartbeats', async () => {
    const encoder = new TextEncoder();
    let controllerRef: ReadableStreamDefaultController<Uint8Array> | null = null;
    const stream = new ReadableStream<Uint8Array>({
      start(controller) {
        controllerRef = controller;
      },
    });
    fetchMock.mockResolvedValue(new Response(stream, { status: 200 }));

    const client = new ChatSSEClient();
    const errors: Error[] = [];
    const chunks: ChatStreamChunk[] = [];
    const streaming = client.streamChat(
      REQUEST,
      c => chunks.push(c),
      e => errors.push(e),
      () => {}
    );

    // Three quiet-but-alive periods, each just under the stall budget.
    for (let i = 0; i < 3; i++) {
      await vi.advanceTimersByTimeAsync(CHAT_SSE_STALL_TIMEOUT_MS - 1_000);
      controllerRef!.enqueue(encoder.encode(': keepalive\n\n'));
      await vi.advanceTimersByTimeAsync(0);
    }
    expect(errors).toHaveLength(0);

    controllerRef!.enqueue(encoder.encode('data: {"type":"done"}\n\n'));
    controllerRef!.close();
    await vi.advanceTimersByTimeAsync(0);
    await streaming;

    expect(errors).toHaveLength(0);
    expect(chunks.map(c => c.type)).toContain('done');
  });

  it('still reports the stall when releasing the socket fails', async () => {
    // `cancel()` rejects on a connection already torn down by the OS — the
    // very situation the watchdog exists for. Releasing is best-effort; it
    // must not replace the stall error with a cancellation failure.
    const stream = new ReadableStream({
      start() {
        /* silent */
      },
      cancel() {
        throw new Error('socket already gone');
      },
    });
    fetchMock.mockResolvedValue(new Response(stream, { status: 200 }));

    const client = new ChatSSEClient();
    const errors: Error[] = [];
    const streaming = client.streamChat(
      REQUEST,
      () => {},
      e => errors.push(e),
      () => {}
    );

    await vi.advanceTimersByTimeAsync(CHAT_SSE_STALL_TIMEOUT_MS + 1_000);
    await streaming;

    expect(errors).toHaveLength(1);
    expect(errorShape(errors[0])).toMatchObject({ name: 'StreamStalledError' });
  });

  it('stops the watchdog once the stream ends normally', async () => {
    fetchMock.mockResolvedValue(sseResponse(['data: {"type":"done"}\n\n']));
    const client = new ChatSSEClient();
    const errors: Error[] = [];
    let done = false;

    await client.streamChat(
      REQUEST,
      () => {},
      e => errors.push(e),
      () => {
        done = true;
      }
    );

    // A leaked timer would abort the *next* run; nothing may remain pending.
    await vi.advanceTimersByTimeAsync(CHAT_SSE_STALL_TIMEOUT_MS * 3);

    expect(done).toBe(true);
    expect(errors).toHaveLength(0);
    expect(vi.getTimerCount()).toBe(0);
  });
});

describe('run-control endpoints', () => {
  it('confirms a cancellation only when the server did cancel', async () => {
    fetchMock.mockResolvedValue(jsonResponse({ cancelled: true }));
    await expect(cancelActiveRun()).resolves.toEqual({ cancelled: true });

    const [url, init] = fetchMock.mock.calls[0];
    expect(String(url)).toMatch(/\/agents\/runs\/active\/cancel$/);
    expect(init).toMatchObject({ method: 'POST', credentials: 'include' });
  });

  it.each([
    ['an ambiguous body', () => jsonResponse({})],
    ['a rejected request', () => new Response(null, { status: 500 })],
  ])('reads %s as "nothing was cancelled"', async (_label, make) => {
    fetchMock.mockResolvedValue(make());
    await expect(cancelActiveRun()).resolves.toEqual({ cancelled: false });
  });

  it('fails closed when the cancel request throws', async () => {
    fetchMock.mockRejectedValue(new Error('offline'));
    await expect(cancelActiveRun()).resolves.toEqual({ cancelled: false });
  });

  it('returns the pending HITL payload untouched', async () => {
    fetchMock.mockResolvedValue(jsonResponse({ question: 'Confirmer ?' }));
    await expect(fetchPendingHitl()).resolves.toEqual({ question: 'Confirmer ?' });
  });

  it.each([
    ['nothing is pending', () => new Response(null, { status: 404 })],
    ['the request throws', () => Promise.reject(new Error('offline'))],
  ])('returns null when %s', async (_label, make) => {
    fetchMock.mockImplementation(() => Promise.resolve(make()));
    await expect(fetchPendingHitl()).resolves.toBeNull();
  });

  it('reports an active run only when it carries a transport id', async () => {
    fetchMock.mockResolvedValue(jsonResponse({ active: true, stream_id: 's-1', run_id: 'r-1' }));
    await expect(fetchActiveRun()).resolves.toEqual({
      active: true,
      stream_id: 's-1',
      run_id: 'r-1',
    });

    // Active without a stream id is unusable — the caller must not reattach.
    fetchMock.mockResolvedValue(jsonResponse({ active: true }));
    await expect(fetchActiveRun()).resolves.toEqual({ active: false });
  });

  it.each([
    ['the endpoint refuses', () => new Response(null, { status: 500 })],
    ['the request throws', () => Promise.reject(new Error('offline'))],
  ])('reads "no active run" when %s', async (_label, make) => {
    fetchMock.mockImplementation(() => Promise.resolve(make()));
    await expect(fetchActiveRun()).resolves.toEqual({ active: false });
  });
});
