/**
 * One call to LIA from a screen (ADR-372): the person can leave it, a newer one replaces it, and a
 * late answer never lands on what moved on. A refusal is told in the section's words.
 */
import { act, renderHook, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { ApiError } from '@/lib/api-client';

const { post } = vi.hoisted(() => ({ post: vi.fn() }));
vi.mock('@/lib/api-client', async importOriginal => ({
  ...(await importOriginal<typeof import('@/lib/api-client')>()),
  default: { post },
}));

import { useAssistCall } from '../useAssistCall';

interface Answer {
  text: string;
  usage: null;
}

/** A call the test answers by hand; aborting it rejects, as the client does. */
function pending() {
  let answer: (value: Answer) => void = () => undefined;
  let signal: AbortSignal | undefined;
  post.mockImplementationOnce(
    (_path: string, _body: unknown, config: { signal: AbortSignal }) =>
      new Promise((resolve, reject) => {
        signal = config.signal;
        answer = resolve;
        config.signal.addEventListener('abort', () => reject(new DOMException('', 'AbortError')));
      })
  );
  return { answer: (value: Answer) => answer(value), signal: () => signal };
}

beforeEach(() => post.mockReset());

describe('useAssistCall', () => {
  it('starts idle', () => {
    const { result } = renderHook(() => useAssistCall<Answer>());

    expect(result.current.state).toEqual({ status: 'idle' });
  });

  it('says it runs, then holds the answer', async () => {
    const call = pending();
    const { result } = renderHook(() => useAssistCall<Answer>());

    act(() => void result.current.run('/tool-assists/mail/summary', { message_id: 'm1' }));
    expect(result.current.state).toEqual({ status: 'running' });
    await act(async () => call.answer({ text: 'ok', usage: null }));

    expect(result.current.state).toEqual({ status: 'done', value: { text: 'ok', usage: null } });
    expect(post.mock.calls[0][0]).toBe('/tool-assists/mail/summary');
    expect(post.mock.calls[0][1]).toEqual({ message_id: 'm1' });
  });

  it('waits past the client’s default: a model takes longer than a list', () => {
    pending();
    const { result } = renderHook(() => useAssistCall<Answer>());

    act(() => void result.current.run('/x', {}));

    expect(post.mock.calls[0][2].timeout).toBeGreaterThan(30_000);
  });

  it('hands the answer to whoever waits on it', async () => {
    const call = pending();
    const { result } = renderHook(() => useAssistCall<Answer>());
    let got: Answer | null = null;

    act(() => {
      void result.current.run('/x', {}).then(value => (got = value));
    });
    await act(async () => call.answer({ text: 'ok', usage: null }));

    expect(got).toEqual({ text: 'ok', usage: null });
  });

  it('tells a refusal in the section’s words', async () => {
    post.mockRejectedValueOnce(new ApiError('refused', 502, { detail: { code: 'assist_failed' } }));
    const { result } = renderHook(() => useAssistCall<Answer>());

    await act(() => result.current.run('/x', {}));

    expect(result.current.state).toEqual({
      status: 'failed',
      refusal: { key: 'workbench.errors.assist_failed' },
    });
  });

  it('leaves it: the request is aborted and nothing remains', async () => {
    const call = pending();
    const { result } = renderHook(() => useAssistCall<Answer>());

    act(() => void result.current.run('/x', {}));
    act(() => result.current.stop());

    expect(call.signal()?.aborted).toBe(true);
    await waitFor(() => expect(result.current.state).toEqual({ status: 'idle' }));
  });

  it('lets a newer call replace it: the older answer never lands', async () => {
    const first = pending();
    const second = pending();
    const { result } = renderHook(() => useAssistCall<Answer>());

    act(() => void result.current.run('/first', {}));
    act(() => void result.current.run('/second', {}));
    expect(first.signal()?.aborted).toBe(true);
    await act(async () => second.answer({ text: 'second', usage: null }));

    expect(result.current.state).toEqual({
      status: 'done',
      value: { text: 'second', usage: null },
    });
  });

  it('asks again what it asked last', async () => {
    post.mockRejectedValueOnce(new Error('lost'));
    post.mockResolvedValueOnce({ text: 'ok', usage: null });
    const { result } = renderHook(() => useAssistCall<Answer>());

    await act(() => result.current.run('/x', { message_id: 'm1' }));
    await act(() => result.current.retry());

    expect(post).toHaveBeenCalledTimes(2);
    expect(post.mock.calls[1][1]).toEqual({ message_id: 'm1' });
    expect(result.current.state).toMatchObject({ status: 'done' });
  });

  it('belongs to what it was asked about: moving on stops it and shows nothing of it', async () => {
    const call = pending();
    const { result, rerender } = renderHook(({ scope }) => useAssistCall<Answer>(scope), {
      initialProps: { scope: 'm1' },
    });

    act(() => void result.current.run('/x', {}));
    rerender({ scope: 'm2' });

    expect(call.signal()?.aborted).toBe(true);
    expect(result.current.state).toEqual({ status: 'idle' });
  });

  it('finds nothing running on coming back to what it left', async () => {
    const call = pending();
    const { result, rerender } = renderHook(({ scope }) => useAssistCall<Answer>(scope), {
      initialProps: { scope: 'm1' },
    });

    act(() => void result.current.run('/x', {}));
    rerender({ scope: 'm2' });
    rerender({ scope: 'm1' });
    await waitFor(() => expect(call.signal()?.aborted).toBe(true));

    expect(result.current.state).toEqual({ status: 'idle' });
  });

  it('keeps an answer it holds when the person comes back to it', async () => {
    post.mockResolvedValueOnce({ text: 'about m1', usage: null });
    const { result, rerender } = renderHook(({ scope }) => useAssistCall<Answer>(scope), {
      initialProps: { scope: 'm1' },
    });

    await act(() => result.current.run('/x', {}));
    rerender({ scope: 'm2' });
    rerender({ scope: 'm1' });

    expect(result.current.state).toMatchObject({ status: 'done' });
  });

  it('shows nothing of an answer once the person moved to another thing', async () => {
    post.mockResolvedValueOnce({ text: 'about m1', usage: null });
    const { result, rerender } = renderHook(({ scope }) => useAssistCall<Answer>(scope), {
      initialProps: { scope: 'm1' },
    });

    await act(() => result.current.run('/x', {}));
    rerender({ scope: 'm2' });

    expect(result.current.state).toEqual({ status: 'idle' });
  });

  it('stops listening when the screen goes away', () => {
    const call = pending();
    const { result, unmount } = renderHook(() => useAssistCall<Answer>());

    act(() => void result.current.run('/x', {}));
    unmount();

    expect(call.signal()?.aborted).toBe(true);
  });
});
