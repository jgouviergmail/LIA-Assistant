/**
 * chat-reducer — SSE connection lifecycle actions.
 *
 * Covers SSE_CONNECTING, SSE_CONNECTED, SSE_DISCONNECTED and SSE_ERROR.
 * Input states are deep-frozen to prove immutability.
 */

import { describe, it, expect } from 'vitest';

import { chatReducer } from '@/reducers/chat-reducer';
import { initialChatState, type ChatState } from '@/types/chat-state';
import { deepFreeze } from '@/__tests__/deep-freeze';

function frozenState(overrides: Partial<ChatState> = {}): ChatState {
  return deepFreeze({ ...structuredClone(initialChatState), ...overrides });
}

describe('chatReducer — SSE lifecycle', () => {
  it('SSE_CONNECTING sets status=sending and sseStatus=connecting', () => {
    const next = chatReducer(frozenState(), { type: 'SSE_CONNECTING' });

    expect(next.status).toBe('sending');
    expect(next.streaming.sseStatus).toBe('connecting');
  });

  it('SSE_CONNECTED updates sseStatus without touching the chat status', () => {
    const state = frozenState({
      status: 'sending',
      streaming: { currentMessageId: null, streamBuffer: '', sseStatus: 'connecting' },
    });

    const next = chatReducer(state, { type: 'SSE_CONNECTED' });

    expect(next.streaming.sseStatus).toBe('connected');
    expect(next.status).toBe('sending');
  });

  it('SSE_DISCONNECTED resets the streaming sub-state and returns to idle', () => {
    const state = frozenState({
      status: 'streaming',
      streaming: { currentMessageId: 'm-1', streamBuffer: 'partial', sseStatus: 'connected' },
    });

    const next = chatReducer(state, { type: 'SSE_DISCONNECTED' });

    expect(next.status).toBe('idle');
    expect(next.streaming).toEqual({
      currentMessageId: null,
      streamBuffer: '',
      sseStatus: 'disconnected',
    });
  });

  it('SSE_ERROR transitions to error state and appends an assistant error bubble', () => {
    const state = frozenState({
      status: 'sending',
      streaming: { currentMessageId: null, streamBuffer: '', sseStatus: 'connecting' },
    });

    const next = chatReducer(state, {
      type: 'SSE_ERROR',
      payload: { error: 'Erreur localisée par le caller' },
    });

    expect(next.status).toBe('error');
    expect(next.streaming.sseStatus).toBe('error');
    expect(next.messages).toHaveLength(1);
    expect(next.messages[0].role).toBe('assistant');
    // The payload arrives ALREADY localized (useChat resolves the i18n key) —
    // the pure reducer must render it verbatim, with no hardcoded prefix in
    // any language (the old inline French prefix was an i18n violation).
    expect(next.messages[0].content).toBe('Erreur localisée par le caller');
    expect(next.messages[0].id).toBeTruthy();
    expect(next.messages[0].timestamp).toBeInstanceOf(Date);
  });
});
