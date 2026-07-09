/**
 * chat-reducer-errors — pure validation helpers used by the useChat dispatch
 * wrapper (dev-only logging). Covers every branch of validateSetMessages,
 * validateStreamToken and validateReducerAction.
 */

import { describe, it, expect } from 'vitest';

import {
  validateSetMessages,
  validateStreamToken,
  validateReducerAction,
} from '@/reducers/chat-reducer-errors';
import { initialChatState, type ChatState } from '@/types/chat-state';
import type { Message } from '@/types/chat';

function makeState(overrides: Partial<ChatState> = {}): ChatState {
  return { ...structuredClone(initialChatState), ...overrides };
}

function makeMessage(id: string): Message {
  return { id, role: 'assistant', content: 'c', timestamp: new Date() };
}

describe('validateSetMessages', () => {
  it('returns null for non-SET_MESSAGES actions', () => {
    expect(validateSetMessages({ type: 'CLEAR_MESSAGES' })).toBeNull();
  });

  it('returns null for a valid array payload', () => {
    const error = validateSetMessages({
      type: 'SET_MESSAGES',
      payload: { messages: [makeMessage('m-1')] },
    });

    expect(error).toBeNull();
  });

  it('flags a non-array payload as a validation error', () => {
    const error = validateSetMessages({
      type: 'SET_MESSAGES',
      payload: { messages: null as unknown as Message[] },
    });

    expect(error).toMatchObject({
      type: 'validation',
      action: 'SET_MESSAGES',
      severity: 'error',
      context: { type: 'object', isNull: true },
    });
  });
});

describe('validateStreamToken', () => {
  const tokenAction = { type: 'STREAM_TOKEN', payload: { token: 'x' } } as const;

  it('returns null for non-STREAM_TOKEN actions', () => {
    expect(validateStreamToken(makeState(), { type: 'CLEAR_MESSAGES' })).toBeNull();
  });

  it('reports a DEBUG-severity state note when no stream is active (late tokens are normal)', () => {
    const error = validateStreamToken(makeState(), tokenAction);

    expect(error).toMatchObject({
      type: 'state',
      action: 'STREAM_TOKEN',
      severity: 'debug',
      context: { sseStatus: 'disconnected' },
    });
  });

  it('reports an ERROR-severity inconsistency when the target message vanished', () => {
    const state = makeState({
      streaming: { currentMessageId: 'ghost', streamBuffer: '', sseStatus: 'connected' },
      messages: [makeMessage('other')],
    });

    const error = validateStreamToken(state, tokenAction);

    expect(error).toMatchObject({
      type: 'state',
      severity: 'error',
      context: { messageId: 'ghost', messageCount: 1 },
    });
  });

  it('returns null when the stream target exists', () => {
    const state = makeState({
      streaming: { currentMessageId: 'm-1', streamBuffer: '', sseStatus: 'connected' },
      messages: [makeMessage('m-1')],
    });

    expect(validateStreamToken(state, tokenAction)).toBeNull();
  });
});

describe('validateReducerAction', () => {
  it('collects the SET_MESSAGES error', () => {
    const errors = validateReducerAction(makeState(), {
      type: 'SET_MESSAGES',
      payload: { messages: 'oops' as unknown as Message[] },
    });

    expect(errors).toHaveLength(1);
    expect(errors[0].action).toBe('SET_MESSAGES');
  });

  it('collects the STREAM_TOKEN error', () => {
    const errors = validateReducerAction(makeState(), {
      type: 'STREAM_TOKEN',
      payload: { token: 'x' },
    });

    expect(errors).toHaveLength(1);
    expect(errors[0].action).toBe('STREAM_TOKEN');
  });

  it('returns an empty list for valid actions', () => {
    const errors = validateReducerAction(makeState(), {
      type: 'SET_MESSAGES',
      payload: { messages: [] },
    });

    expect(errors).toEqual([]);
  });

  it('returns an empty list for a STREAM_TOKEN targeting an existing stream', () => {
    const state = makeState({
      streaming: { currentMessageId: 'm-1', streamBuffer: '', sseStatus: 'connected' },
      messages: [makeMessage('m-1')],
    });

    expect(validateReducerAction(state, { type: 'STREAM_TOKEN', payload: { token: 'x' } })).toEqual(
      []
    );
  });

  it('returns an empty list for action types without a validator', () => {
    expect(validateReducerAction(makeState(), { type: 'CLEAR_MESSAGES' })).toEqual([]);
  });
});
