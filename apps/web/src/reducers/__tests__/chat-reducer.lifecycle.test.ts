/**
 * chat-reducer — message lifecycle actions.
 *
 * Covers SEND_MESSAGE, CLEAR_MESSAGES, SET_MESSAGES (including the
 * streaming-message preservation guard), APPEND_MESSAGE deduplication and
 * SET_API_AVAILABLE. Input states are deep-frozen to prove immutability:
 * any in-place mutation inside the reducer throws in strict mode.
 *
 * Complements (does not duplicate) the existing focused suites:
 * chat-reducer.compaction / .context-usage / .hitl-token-guard.
 */

import { describe, it, expect } from 'vitest';

import { chatReducer } from '@/reducers/chat-reducer';
import { initialChatState, type ChatState } from '@/types/chat-state';
import type { Message } from '@/types/chat';
import { deepFreeze } from '@/__tests__/deep-freeze';

function makeMessage(
  id: string,
  role: Message['role'] = 'user',
  content = `content-${id}`
): Message {
  return { id, role, content, timestamp: new Date() };
}

function frozenState(overrides: Partial<ChatState> = {}): ChatState {
  return deepFreeze({ ...structuredClone(initialChatState), ...overrides });
}

describe('chatReducer — SEND_MESSAGE', () => {
  it('appends the user message and transitions idle → sending / connecting', () => {
    const state = frozenState();
    const message = makeMessage('u-1');

    const next = chatReducer(state, { type: 'SEND_MESSAGE', payload: { message } });

    expect(next.messages).toEqual([message]);
    expect(next.status).toBe('sending');
    expect(next.streaming.sseStatus).toBe('connecting');
  });

  it('clears stale per-request state (debug metrics, screenshot, compaction)', () => {
    const state = frozenState({
      currentDebugMetrics: {
        query_info: { original_query: 'q' },
      } as ChatState['currentDebugMetrics'],
      browserScreenshot: { image_base64: 'abc', url: 'https://x', title: 't' },
      compaction: { phase: 'done' },
    });

    const next = chatReducer(state, {
      type: 'SEND_MESSAGE',
      payload: { message: makeMessage('u-2') },
    });

    expect(next.currentDebugMetrics).toBeNull();
    expect(next.browserScreenshot).toBeNull();
    expect(next.compaction).toBeNull();
  });

  it('preserves prior messages and conversation totals', () => {
    const existing = makeMessage('a-1', 'assistant');
    const state = frozenState({
      messages: [existing],
      totals: { ...initialChatState.totals, totalTokensIn: 42 },
    });

    const next = chatReducer(state, {
      type: 'SEND_MESSAGE',
      payload: { message: makeMessage('u-3') },
    });

    expect(next.messages[0]).toBe(existing);
    expect(next.messages).toHaveLength(2);
    expect(next.totals.totalTokensIn).toBe(42);
  });
});

describe('chatReducer — CLEAR_MESSAGES', () => {
  it('resets messages, status, streaming, totals, registry and debug state', () => {
    const state = frozenState({
      messages: [makeMessage('u-1'), makeMessage('a-1', 'assistant')],
      status: 'streaming',
      streaming: {
        currentMessageId: 'a-1',
        streamBuffer: 'partial',
        sseStatus: 'connected',
        phase: 'answer',
      },
      totals: {
        totalTokensIn: 10,
        totalTokensOut: 20,
        totalTokensCache: 5,
        totalCostEur: 0.5,
        totalMessages: 3,
        totalGoogleApiRequests: 2,
      },
      registry: {
        item_1: {
          id: 'item_1',
          type: 'CONTACT',
          payload: {},
          meta: { source: 'google_contacts', timestamp: '2026-07-09T00:00:00Z' },
        },
      },
      currentDebugMetrics: { query_info: {} } as ChatState['currentDebugMetrics'],
      debugMetricsHistory: [
        { id: 'h1', timestamp: new Date(), query: 'q', metrics: {} },
      ] as ChatState['debugMetricsHistory'],
      browserScreenshot: { image_base64: 'x', url: 'https://x', title: 't' },
    });

    const next = chatReducer(state, { type: 'CLEAR_MESSAGES' });

    expect(next.messages).toEqual([]);
    expect(next.status).toBe('idle');
    expect(next.streaming).toEqual({
      currentMessageId: null,
      streamBuffer: '',
      sseStatus: 'disconnected',
      phase: 'answer',
    });
    expect(next.totals).toEqual(initialChatState.totals);
    expect(next.registry).toEqual({});
    expect(next.currentDebugMetrics).toBeNull();
    expect(next.debugMetricsHistory).toEqual([]);
    expect(next.browserScreenshot).toBeNull();
  });
});

describe('chatReducer — SET_MESSAGES', () => {
  it('replaces the whole messages array', () => {
    const state = frozenState({ messages: [makeMessage('old-1')] });
    const fresh = [makeMessage('new-1'), makeMessage('new-2', 'assistant')];

    const next = chatReducer(state, { type: 'SET_MESSAGES', payload: { messages: fresh } });

    expect(next.messages).toEqual(fresh);
  });

  it('coerces a non-array payload to an empty list (defensive)', () => {
    const state = frozenState({ messages: [makeMessage('old-1')] });

    const next = chatReducer(state, {
      type: 'SET_MESSAGES',
      payload: { messages: null as unknown as Message[] },
    });

    expect(next.messages).toEqual([]);
  });

  it('re-appends the in-flight streaming message when the reload omits it', () => {
    // Race guard: a history reload (e.g. reminder notification) must not drop
    // the assistant message currently being streamed (not yet persisted).
    const streamingMsg = makeMessage('stream-1', 'assistant', 'partial answer');
    const state = frozenState({
      status: 'streaming',
      streaming: {
        currentMessageId: 'stream-1',
        streamBuffer: 'partial answer',
        sseStatus: 'connected',
        phase: 'answer',
      },
      messages: [makeMessage('u-1'), streamingMsg],
    });
    const reloaded = [makeMessage('u-1'), makeMessage('r-1', 'assistant')];

    const next = chatReducer(state, { type: 'SET_MESSAGES', payload: { messages: reloaded } });

    expect(next.messages).toHaveLength(3);
    expect(next.messages[2]).toBe(streamingMsg);
  });

  it('does NOT duplicate the streaming message when the reload already contains it', () => {
    const streamingMsg = makeMessage('stream-1', 'assistant', 'partial');
    const state = frozenState({
      status: 'streaming',
      streaming: {
        currentMessageId: 'stream-1',
        streamBuffer: 'partial',
        sseStatus: 'connected',
        phase: 'answer',
      },
      messages: [streamingMsg],
    });
    const reloaded = [makeMessage('u-1'), makeMessage('stream-1', 'assistant', 'persisted')];

    const next = chatReducer(state, { type: 'SET_MESSAGES', payload: { messages: reloaded } });

    expect(next.messages).toEqual(reloaded);
  });

  it('falls through to plain replacement when currentMessageId matches no message', () => {
    const state = frozenState({
      status: 'streaming',
      streaming: {
        currentMessageId: 'ghost',
        streamBuffer: '',
        sseStatus: 'connected',
        phase: 'answer',
      },
      messages: [makeMessage('u-1')],
    });
    const reloaded = [makeMessage('n-1')];

    const next = chatReducer(state, { type: 'SET_MESSAGES', payload: { messages: reloaded } });

    expect(next.messages).toEqual(reloaded);
  });
});

describe('chatReducer — APPEND_MESSAGE', () => {
  it('appends a new message', () => {
    const state = frozenState({ messages: [makeMessage('u-1')] });
    const incoming = makeMessage('n-1', 'assistant');

    const next = chatReducer(state, { type: 'APPEND_MESSAGE', payload: { message: incoming } });

    expect(next.messages).toHaveLength(2);
    expect(next.messages[1]).toBe(incoming);
  });

  it('ignores a duplicate id (returns the same state reference)', () => {
    const existing = makeMessage('dup-1');
    const state = frozenState({ messages: [existing] });

    const next = chatReducer(state, {
      type: 'APPEND_MESSAGE',
      payload: { message: makeMessage('dup-1', 'assistant', 'other content') },
    });

    expect(next).toBe(state);
  });
});

describe('chatReducer — SET_API_AVAILABLE', () => {
  it('sets availability to true and back to false', () => {
    const state = frozenState();

    const up = chatReducer(state, { type: 'SET_API_AVAILABLE', payload: { available: true } });
    expect(up.apiAvailable).toBe(true);

    const down = chatReducer(deepFreeze(up), {
      type: 'SET_API_AVAILABLE',
      payload: { available: false },
    });
    expect(down.apiAvailable).toBe(false);
  });
});
