/**
 * One call to LIA from a screen (ADR-372): the person can leave it, a newer one replaces it, and a
 * late answer never lands on what moved on. A refusal is told in the section's words.
 */
import { act, renderHook, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { createElement, type ContextType, type ReactNode } from 'react';
import { AuthContext, type User } from '@/lib/auth';
import { makeUser } from '@/__tests__/factories';

import { ApiError } from '@/lib/api-client';

const { post } = vi.hoisted(() => ({ post: vi.fn() }));
vi.mock('@/lib/api-client', async importOriginal => ({
  ...(await importOriginal<typeof import('@/lib/api-client')>()),
  default: { post },
}));

import { useAssistCall } from '@/hooks/useAssistCall';

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
  it('aborts and forgets the same scope when the account changes or signs out', async () => {
    let user: User | null = makeUser({ id: 'one' });
    function Session({ children }: { children: ReactNode }) {
      const auth: NonNullable<ContextType<typeof AuthContext>> = {
        user,
        isLoading: false,
        login: vi.fn(),
        verifyMfa: vi.fn(),
        register: vi.fn(),
        logout: vi.fn(),
        initiateGoogleOAuth: vi.fn(),
        completeNativeSignIn: vi.fn(),
        refreshUser: vi.fn(),
        applyUserUpdate: vi.fn(),
      };
      return createElement(AuthContext.Provider, { value: auth }, children);
    }
    const first = pending();
    const { result, rerender } = renderHook(() => useAssistCall<Answer>('same'), {
      wrapper: Session,
    });
    const old = result.current;
    act(() => {
      void old.run('/x', { private: 'one' });
    });
    user = makeUser({ id: 'two' });
    rerender();
    expect(first.signal()?.aborted).toBe(true);
    user = null;
    rerender();
    user = makeUser({ id: 'one' });
    rerender();
    await act(() => old.retry());
    expect(post).toHaveBeenCalledOnce();
    expect(result.current.state.status).toBe('idle');
  });
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

  it('forgets an answer when its scope left, including an A-B-A return', async () => {
    post.mockResolvedValueOnce({ text: 'about m1', usage: null });
    const { result, rerender } = renderHook(({ scope }) => useAssistCall<Answer>(scope), {
      initialProps: { scope: 'm1' },
    });

    await act(() => result.current.run('/x', {}));
    rerender({ scope: 'm2' });
    rerender({ scope: 'm1' });

    expect(result.current.state).toMatchObject({ status: 'idle' });
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

  it('forgets the retry payload on stop', async () => {
    post.mockRejectedValueOnce(new Error('lost'));
    const { result } = renderHook(() => useAssistCall<Answer>('one'));
    await act(() => result.current.run('/x', { private: 'one' }));
    act(() => result.current.stop());
    await act(() => result.current.retry());
    expect(post).toHaveBeenCalledTimes(1);
  });

  it('a retained callback cannot start or retry an obsolete scope', async () => {
    post.mockRejectedValueOnce(new Error('lost'));
    const { result, rerender } = renderHook(({ scope }) => useAssistCall<Answer>(scope), {
      initialProps: { scope: 'one' },
    });
    const old = result.current;
    await act(() => old.run('/x', { private: 'one' }));
    rerender({ scope: 'two' });
    rerender({ scope: 'one' });
    await act(() => old.retry());
    await act(() => old.run('/x', {}));
    expect(post).toHaveBeenCalledTimes(1);
  });
});
