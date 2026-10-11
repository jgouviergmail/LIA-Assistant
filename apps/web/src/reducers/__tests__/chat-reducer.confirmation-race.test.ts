import { describe, expect, it } from 'vitest';
import { chatReducer } from '@/reducers/chat-reducer';
import { initialChatState } from '@/types/chat-state';
import type { Message } from '@/types/chat';
import { deepFreeze } from '@/__tests__/deep-freeze';

const timestamp = new Date('2026-10-11T00:00:00Z');
const row = 'saved-answer';
const text = 'Réglages de l’application enregistrés';

describe('confirmation completion racing with history refresh', () => {
  it('keeps one live answer when its archived row arrived before done', () => {
    const state = deepFreeze({
      ...structuredClone(initialChatState),
      messages: [
        { id: row, role: 'assistant', content: text, timestamp, metadata: { message_db_id: row } },
        { id: 'stream', role: 'assistant', content: text, timestamp },
      ] as Message[],
    });
    const result = chatReducer(state, {
      type: 'STREAM_DONE',
      payload: {
        messageId: 'stream',
        metadata: { archived_message_id: row, run_id: 'confirmation' },
      },
    });
    expect(result.messages).toHaveLength(1);
    expect(result.messages[0].id).toBe('stream');
    expect(result.messages[0].metadata?.message_db_id).toBe(row);
    expect(state.messages).toHaveLength(2);
  });

  it('preserves a different saved answer with identical words', () => {
    const state = {
      ...structuredClone(initialChatState),
      messages: [
        {
          id: 'previous',
          role: 'assistant',
          content: text,
          timestamp,
          metadata: { message_db_id: 'previous' },
        },
        { id: row, role: 'assistant', content: text, timestamp, metadata: { message_db_id: row } },
        { id: 'stream', role: 'assistant', content: text, timestamp },
      ] as Message[],
    };
    const result = chatReducer(state, {
      type: 'STREAM_DONE',
      payload: {
        messageId: 'stream',
        metadata: { archived_message_id: row },
      },
    });
    expect(result.messages.map(message => message.id)).toEqual(['previous', 'stream']);
  });

  it('does not collapse ambiguous done events without a target stream', () => {
    const state = {
      ...structuredClone(initialChatState),
      messages: [
        {
          id: 'previous',
          role: 'assistant',
          content: text,
          timestamp,
          metadata: { message_db_id: 'previous' },
        },
        { id: row, role: 'assistant', content: text, timestamp, metadata: { message_db_id: row } },
      ] as Message[],
    };
    expect(
      chatReducer(state, {
        type: 'STREAM_DONE',
        payload: {
          messageId: 'missing-stream',
          metadata: { archived_message_id: row },
        },
      }).messages
    ).toHaveLength(2);
  });
});
