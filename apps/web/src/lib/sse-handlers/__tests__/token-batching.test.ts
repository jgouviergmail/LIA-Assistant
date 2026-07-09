/**
 * Tests for SSE token batching in processSSEChunk.
 *
 * Raw tokens are coalesced and flushed once per animation frame instead of
 * dispatching (and re-parsing the whole markdown message) per token. Ordering
 * guarantee: any non-token chunk synchronously flushes buffered tokens BEFORE
 * its own handler runs.
 */

import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';

import { flushTokenBatching, processSSEChunk, resetTokenBatching } from '@/lib/sse-handlers';
import type { SSEHandlerContext } from '@/lib/sse-handlers/types';
import type { ChatStreamChunk } from '@/types/chat';

function buildContext(): { context: SSEHandlerContext; dispatch: ReturnType<typeof vi.fn> } {
  const dispatch = vi.fn();
  let normalStreamInitialized = true; // "stream already started" path → plain STREAM_TOKEN
  const context = {
    dispatch,
    withContext: (extra: Record<string, unknown>) => extra,
    t: (key: string) => key,
    progressMessageId: null,
    setProgressMessageId: vi.fn(),
    assistantMessageId: 'assistant-1',
    get normalStreamInitialized() {
      return normalStreamInitialized;
    },
    setNormalStreamInitialized: (v: boolean) => {
      normalStreamInitialized = v;
    },
    executionStepsRef: { current: [] },
    emittedStepKeysRef: { current: new Set<string>() },
    reasoningBufRef: { current: '' },
  } as unknown as SSEHandlerContext;
  return { context, dispatch };
}

function token(content: string): ChatStreamChunk {
  return { type: 'token', content } as ChatStreamChunk;
}

describe('processSSEChunk — token batching', () => {
  let rafCallbacks: FrameRequestCallback[];

  beforeEach(() => {
    rafCallbacks = [];
    vi.stubGlobal('requestAnimationFrame', (cb: FrameRequestCallback) => {
      rafCallbacks.push(cb);
      return rafCallbacks.length;
    });
    vi.stubGlobal('cancelAnimationFrame', vi.fn());
    resetTokenBatching();
  });

  afterEach(() => {
    resetTokenBatching();
    vi.unstubAllGlobals();
  });

  it('coalesces multiple tokens into a single dispatch on the animation frame', () => {
    const { context, dispatch } = buildContext();

    processSSEChunk(token('Hel'), context);
    processSSEChunk(token('lo '), context);
    processSSEChunk(token('world'), context);

    // Nothing dispatched yet — tokens are buffered
    expect(dispatch).not.toHaveBeenCalled();
    expect(rafCallbacks).toHaveLength(1); // one scheduled flush, not three

    rafCallbacks[0](0);

    expect(dispatch).toHaveBeenCalledTimes(1);
    expect(dispatch).toHaveBeenCalledWith({
      type: 'STREAM_TOKEN',
      payload: { token: 'Hello world' },
    });
  });

  it('flushes buffered tokens BEFORE handling a non-token chunk (ordering)', () => {
    const { context, dispatch } = buildContext();

    processSSEChunk(token('partial answer'), context);
    expect(dispatch).not.toHaveBeenCalled();

    // A done chunk arrives before the animation frame fired
    processSSEChunk(
      { type: 'done', content: { message: 'final', metadata: {} } } as unknown as ChatStreamChunk,
      context
    );

    // First call = the flushed token, before the done handler's dispatches
    expect(dispatch.mock.calls[0][0]).toEqual({
      type: 'STREAM_TOKEN',
      payload: { token: 'partial answer' },
    });
    // The late animation frame must not re-dispatch anything
    const callsAfterDone = dispatch.mock.calls.length;
    rafCallbacks.forEach(cb => cb(0));
    expect(dispatch.mock.calls.length).toBe(callsAfterDone);
  });

  it('preserves the first-token STREAM_REPLACE path (progress message replacement)', () => {
    const { context, dispatch } = buildContext();
    (context as { progressMessageId: string | null }).progressMessageId = 'progress-1';
    context.setNormalStreamInitialized(false);

    processSSEChunk(token('Bon'), context);
    processSSEChunk(token('jour'), context);
    rafCallbacks[0](0);

    expect(dispatch).toHaveBeenCalledTimes(1);
    expect(dispatch).toHaveBeenCalledWith({
      type: 'STREAM_REPLACE',
      payload: { content: 'Bonjour' },
    });
  });

  it('resetTokenBatching drops buffered tokens without dispatching (stale stream)', () => {
    const { context, dispatch } = buildContext();

    processSSEChunk(token('stale'), context);
    resetTokenBatching();
    rafCallbacks.forEach(cb => cb(0));

    expect(dispatch).not.toHaveBeenCalled();
  });

  it('drops empty tokens without scheduling a flush', () => {
    const { context, dispatch } = buildContext();

    processSSEChunk(token(''), context);

    expect(rafCallbacks).toHaveLength(0);
    expect(dispatch).not.toHaveBeenCalled();
  });

  it('flushTokenBatching dispatches buffered tokens synchronously (stream-error path)', () => {
    const { context, dispatch } = buildContext();

    processSSEChunk(token('before '), context);
    processSSEChunk(token('the error'), context);
    expect(dispatch).not.toHaveBeenCalled();

    flushTokenBatching();

    expect(dispatch).toHaveBeenCalledTimes(1);
    expect(dispatch).toHaveBeenCalledWith({
      type: 'STREAM_TOKEN',
      payload: { token: 'before the error' },
    });

    // The already-consumed animation frame must not re-dispatch anything.
    rafCallbacks.forEach(cb => cb(0));
    expect(dispatch).toHaveBeenCalledTimes(1);
  });

  it('flushTokenBatching is a no-op on an empty buffer', () => {
    const { dispatch } = buildContext();

    flushTokenBatching();

    expect(dispatch).not.toHaveBeenCalled();
  });

  it('degrades to synchronous dispatch when requestAnimationFrame is unavailable (SSR)', () => {
    const { context, dispatch } = buildContext();
    vi.stubGlobal('requestAnimationFrame', undefined);

    processSSEChunk(token('sync'), context);

    expect(dispatch).toHaveBeenCalledTimes(1);
    expect(dispatch).toHaveBeenCalledWith({
      type: 'STREAM_TOKEN',
      payload: { token: 'sync' },
    });
  });

  it('routes unknown chunk types to the debug log without throwing', () => {
    const { context, dispatch } = buildContext();

    expect(() =>
      processSSEChunk(
        { type: 'some_future_event', content: 'x' } as unknown as ChatStreamChunk,
        context
      )
    ).not.toThrow();
    expect(dispatch).not.toHaveBeenCalled();
  });
});
