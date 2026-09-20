/**
 * useLiveChatBindings — the chat's doors as the live session sees them: the
 * request goes through `sendMessage` with the live meta in LAST position, and
 * the answer is read from the CURRENT thread (never from the mount-time one),
 * a pending HITL question standing as the answer.
 */
import { describe, it, expect, vi } from 'vitest';
import { act, renderHook } from '@testing-library/react';

import type { Message } from '@/types/chat';

import { readLastAnswer, useLiveChatBindings, type LiveChatSource } from '../useLiveChatBindings';

type Answer = { text: string; pendingQuestion: string | null; register?: string | null };

function message(
  role: 'user' | 'assistant',
  content: string,
  metadata?: Record<string, unknown>
): Message {
  return { id: `${role}-${content}`, role, content, timestamp: new Date(), metadata };
}

describe('readLastAnswer', () => {
  it('reads the last assistant row, ignoring later user rows', () => {
    const rows = [message('user', 'q'), message('assistant', 'a1'), message('user', 'q2')];
    expect(readLastAnswer(rows, 'none')).toEqual({
      text: 'a1',
      pendingQuestion: null,
      register: null,
    });
  });

  it('says which register the answer was said in, and none for a row without one', () => {
    // ADR-253: the register the answering model declared reaches the live
    // bridge as the voice's delivery note; a malformed annotation is no register.
    const worn = message('assistant', 'a1', {
      expressivity: { register: 'warm', intensity: 0.6, accent: 'nod' },
    });
    expect(readLastAnswer([worn], 'none').register).toBe('warm');
    expect(
      readLastAnswer([message('assistant', 'a2', { expressivity: 'warm' })], 'none').register
    ).toBeNull();
    expect(
      readLastAnswer([message('assistant', 'a3', { expressivity: { register: '' } })], 'none')
        .register
    ).toBeNull();
    // A pending question keeps its register too.
    expect(readLastAnswer([worn], 'awaiting')).toEqual({
      text: '',
      pendingQuestion: 'a1',
      register: 'warm',
    });
  });

  it('turns the last row into a pending question while HITL awaits the person', () => {
    const rows = [message('user', 'q'), message('assistant', 'Send it to Alex?')];
    expect(readLastAnswer(rows, 'awaiting')).toEqual({
      text: '',
      pendingQuestion: 'Send it to Alex?',
      register: null,
    });
    expect(readLastAnswer(rows, 'submitting').pendingQuestion).toBe('Send it to Alex?');
  });

  it('answers nothing on an empty thread', () => {
    expect(readLastAnswer([], 'none')).toEqual({
      text: '',
      pendingQuestion: null,
      register: null,
    });
  });
});

describe('useLiveChatBindings', () => {
  function source(messages: Message[]): LiveChatSource {
    return {
      messages,
      hitl: { status: 'none' },
      sendMessage: vi.fn(async () => {}),
      appendMessage: vi.fn(),
      stopGeneration: vi.fn(async () => {}),
    };
  }

  it('sends the request with the live meta as the seventh argument', async () => {
    const chat = source([]);
    const { result } = renderHook(() => useLiveChatBindings(chat));
    await result.current.sendMessage('agenda?', { live_session_id: 's', spoken_text: 'hey' });
    expect(chat.sendMessage).toHaveBeenCalledWith(
      'agenda?',
      undefined,
      undefined,
      undefined,
      undefined,
      undefined,
      { live_session_id: 's', spoken_text: 'hey' }
    );
  });

  it('hands the chat Stop through, so a replaced delegation can kill its turn', async () => {
    const chat = source([]);
    const { result } = renderHook(() => useLiveChatBindings(chat));
    await result.current.stop();
    expect(chat.stopGeneration).toHaveBeenCalledTimes(1);
  });

  it('reads the thread as it is NOW, through a stable bindings object', async () => {
    const first = source([message('assistant', 'old')]);
    const { result, rerender } = renderHook(props => useLiveChatBindings(props), {
      initialProps: first,
    });
    const bindings = result.current;
    rerender({ ...first, messages: [message('assistant', 'new')] });
    expect(result.current).toBe(bindings);
    let pending: Promise<Answer> | null = null;
    // The reader forces a render; `act` flushes it, and the effect serves the reader.
    await act(async () => {
      pending = bindings.readAnswer();
    });
    expect(await pending).toEqual({ text: 'new', pendingQuestion: null, register: null });
  });

  it('serves a reader with the state committed AFTER it asked, never a stale one', async () => {
    // The chat's `sendMessage` resolves the instant the stream ends, one
    // render before the thread holds the final tokens: a reader queued at
    // that instant must be served by the NEXT commit.
    const initial = source([message('assistant', 'partial')]);
    const { result, rerender } = renderHook(props => useLiveChatBindings(props), {
      initialProps: initial,
    });
    let pending: Promise<Answer> | null = null;
    await act(async () => {
      pending = result.current.readAnswer();
      rerender({ ...initial, messages: [message('assistant', 'partial and final')] });
    });
    expect(await pending).toEqual({
      text: 'partial and final',
      pendingQuestion: null,
      register: null,
    });
  });
});
