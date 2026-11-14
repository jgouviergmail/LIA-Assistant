/**
 * A send the server kept as a waiting message leaves the thread (ADR-384).
 *
 * The optimistic bubble was the person's message going out; once the busy
 * account turned it into a waiting message, the bubble below the thread is its
 * only face — leaving it in the thread would show the words twice.
 */
import { describe, expect, it } from 'vitest';

import { chatReducer } from '@/reducers/chat-reducer';
import { initialChatState, type ChatState } from '@/types/chat-state';
import type { Message } from '@/types/chat';

function message(id: string, role: Message['role']): Message {
  return { id, content: id, role, timestamp: new Date('2026-11-13T15:00:00Z') };
}

describe('chatReducer — WITHDRAW_MESSAGE', () => {
  it('removes the optimistic send and returns to idle', () => {
    const answer = message('answer', 'assistant');
    const sent = message('sent', 'user');
    let state: ChatState = { ...initialChatState, messages: [answer] };
    state = chatReducer(state, { type: 'SEND_MESSAGE', payload: { message: sent } });
    expect(state.status).toBe('sending');

    const next = chatReducer(state, { type: 'WITHDRAW_MESSAGE', payload: { id: 'sent' } });

    expect(next.messages).toEqual([answer]);
    expect(next.status).toBe('idle');
    expect(next.streaming.sseStatus).toBe('disconnected');
  });

  it('leaves a thread without that message unchanged', () => {
    const answer = message('answer', 'assistant');
    const state: ChatState = { ...initialChatState, messages: [answer] };
    const next = chatReducer(state, { type: 'WITHDRAW_MESSAGE', payload: { id: 'other' } });
    expect(next.messages).toEqual([answer]);
  });
});
