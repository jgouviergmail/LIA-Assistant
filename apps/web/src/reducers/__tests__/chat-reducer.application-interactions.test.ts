import { describe, expect, it } from 'vitest';
import { chatReducer } from '@/reducers/chat-reducer';
import { initialChatState, type ChatState } from '@/types/chat-state';
import { deepFreeze } from '@/__tests__/deep-freeze';

describe('secure application references in delivered messages', () => {
  it('preserves the same owned references as archived history without rendering them as performed effects', () => {
    const references = [{ command_id: 'aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa' }];
    const state: ChatState = deepFreeze({ ...structuredClone(initialChatState),
      messages: [{ id: 'answer', role: 'assistant', content: 'Waiting for secure authentication', timestamp: new Date() }] });
    const result = chatReducer(state, { type: 'STREAM_DONE', payload: {
      messageId: 'answer', metadata: { application_interactions: references },
    } });
    expect(result.messages[0].metadata?.application_interactions).toEqual(references);
    expect(result.messages[0].performedEffects).toBeUndefined();
    expect(state.messages[0].metadata).toBeUndefined();
  });
});
