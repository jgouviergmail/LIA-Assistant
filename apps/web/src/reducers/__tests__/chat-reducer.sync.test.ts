/**
 * chat-reducer — keeping the thread in sync with the server (ADR-320).
 *
 * MERGE_SERVER_PAGE hands the merge to `lib/chat-merge.ts` (tested there); this
 * suite pins what the reducer adds around it: a merge that changes nothing is
 * no state change at all (React skips the render), and a `done` teaches the
 * live question the archived row it became. Input states are deep-frozen.
 */

import { describe, expect, it } from 'vitest';

import { chatReducer } from '@/reducers/chat-reducer';
import { initialChatState, type ChatState } from '@/types/chat-state';
import type { Message } from '@/types/chat';
import { deepFreeze } from '@/__tests__/deep-freeze';

const AT = new Date('2026-09-25T10:00:00Z');

function historyRow(id: string, role: Message['role'] = 'assistant'): Message {
  return { id, role, content: `row ${id}`, timestamp: AT, metadata: { message_db_id: id } };
}

function frozenState(overrides: Partial<ChatState> = {}): ChatState {
  return deepFreeze({ ...structuredClone(initialChatState), ...overrides });
}

describe('chatReducer — MERGE_SERVER_PAGE', () => {
  it('returns the SAME state when the page brings nothing new', () => {
    const state = frozenState({ messages: [historyRow('a')] });

    const next = chatReducer(state, {
      type: 'MERGE_SERVER_PAGE',
      payload: { messages: [historyRow('a')] },
    });

    expect(next).toBe(state);
  });

  it('adds what arrived without touching the bubbles already there', () => {
    const state = frozenState({ messages: [historyRow('a')] });

    const next = chatReducer(state, {
      type: 'MERGE_SERVER_PAGE',
      payload: { messages: [historyRow('a'), historyRow('b')] },
    });

    expect(next.messages.map(m => m.id)).toEqual(['a', 'b']);
    expect(next.messages[0]).toBe(state.messages[0]);
  });
});

describe('chatReducer — STREAM_DONE names the archived question', () => {
  const question: Message = { id: 'client-u', role: 'user', content: 'Hi', timestamp: AT };
  const answer: Message = { id: 'client-a', role: 'assistant', content: 'Hello', timestamp: AT };

  it('teaches the live question the row it became', () => {
    const state = frozenState({ messages: [historyRow('old'), question, answer] });

    const next = chatReducer(state, {
      type: 'STREAM_DONE',
      payload: {
        messageId: 'client-a',
        metadata: { archived_message_id: 'a1', archived_user_message_id: 'u1' },
      },
    });

    expect(next.messages[1].metadata?.message_db_id).toBe('u1');
    expect(next.messages[2].metadata?.message_db_id).toBe('a1');
    // An older bubble is never renamed.
    expect(next.messages[0].metadata?.message_db_id).toBe('old');
  });

  it('never gives the row of the question to a live-session row appended after the answer', () => {
    const spoken: Message = {
      id: 'lt1',
      role: 'user',
      content: 'Et demain ?',
      timestamp: AT,
      metadata: { type: 'live_turn' },
    };
    const state = frozenState({ messages: [question, answer, spoken] });

    const next = chatReducer(state, {
      type: 'STREAM_DONE',
      payload: {
        messageId: 'client-a',
        metadata: { archived_message_id: 'a1', archived_user_message_id: 'u1' },
      },
    });

    expect(next.messages[0].metadata?.message_db_id).toBe('u1');
    expect(next.messages[2].metadata?.message_db_id).toBeUndefined();
  });

  it('names nothing when the question could not be archived', () => {
    const state = frozenState({ messages: [question, answer] });

    const next = chatReducer(state, {
      type: 'STREAM_DONE',
      payload: { messageId: 'client-a', metadata: { archived_message_id: 'a1' } },
    });

    expect(next.messages[0].metadata?.message_db_id).toBeUndefined();
  });

  it('never renames a question that already names its own row', () => {
    const state = frozenState({ messages: [historyRow('u0', 'user'), answer] });

    const next = chatReducer(state, {
      type: 'STREAM_DONE',
      payload: {
        messageId: 'client-a',
        metadata: { archived_message_id: 'a1', archived_user_message_id: 'u1' },
      },
    });

    expect(next.messages[0].metadata?.message_db_id).toBe('u0');
  });

  it('names the last question when the answer bubble is no longer on screen', () => {
    // A `done` can outlive its bubble (another tab reset the thread mid-stream):
    // the question is then the last user bubble of the thread.
    const state = frozenState({ messages: [historyRow('old'), question] });

    const next = chatReducer(state, {
      type: 'STREAM_DONE',
      payload: {
        messageId: 'client-a',
        metadata: { archived_message_id: 'a1', archived_user_message_id: 'u1' },
      },
    });

    expect(next.messages[1].metadata?.message_db_id).toBe('u1');
    expect(next.messages[0].metadata?.message_db_id).toBe('old');
  });

  it('walks back past the bubbles between the question and its answer', () => {
    // A HITL question LIA asked sits between the person's question and the
    // answer that followed the approval: it is not the question.
    const asked: Message = {
      id: 'hitl_1',
      role: 'assistant',
      content: 'Confirm?',
      timestamp: AT,
    };
    const state = frozenState({ messages: [question, asked, answer] });

    const next = chatReducer(state, {
      type: 'STREAM_DONE',
      payload: {
        messageId: 'client-a',
        metadata: { archived_message_id: 'a1', archived_user_message_id: 'u1' },
      },
    });

    expect(next.messages[0].metadata?.message_db_id).toBe('u1');
    expect(next.messages[1].metadata?.message_db_id).toBeUndefined();
  });

  it('names nothing when no question precedes the answer', () => {
    const state = frozenState({ messages: [answer] });

    const next = chatReducer(state, {
      type: 'STREAM_DONE',
      payload: {
        messageId: 'client-a',
        metadata: { archived_message_id: 'a1', archived_user_message_id: 'u1' },
      },
    });

    expect(next.messages.every(m => m.metadata?.message_db_id !== 'u1')).toBe(true);
  });

  it('never gives one row to two bubbles', () => {
    const named: Message = { ...question, metadata: { message_db_id: 'u1' } };
    const state = frozenState({ messages: [named, answer] });

    const next = chatReducer(state, {
      type: 'STREAM_DONE',
      payload: {
        messageId: 'client-a',
        metadata: { archived_message_id: 'a1', archived_user_message_id: 'u1' },
      },
    });

    expect(next.messages[0]).toEqual(named);
  });
});
