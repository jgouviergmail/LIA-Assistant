import { describe, it, expect } from 'vitest';
import { chatReducer } from '../chat-reducer';
import { initialChatState } from '@/types/chat-state';
import type { Message } from '@/types/chat';
import type { CardActionsProjection, CardCompositionWire } from '@/types/card-actions';

const projection: CardActionsProjection = {
  version: 1,
  run_id: 'current',
  items: [
    {
      registry_id: 'email_a',
      kind: 'EMAIL',
      target_id: 'target',
      provider: 'google_gmail',
      account_binding: '00000000-0000-0000-0000-000000000004',
      label: 'Subject',
      actions: ['reply', 'forward'],
    },
  ],
};
const selection: CardCompositionWire = {
  version: 1,
  message_id: '00000000-0000-0000-0000-000000000003',
  run_id: 'source',
  registry_id: 'email_a',
  action: 'reply',
};
const answer = (id: string, run = 'current'): Message => ({
  id,
  role: 'assistant',
  content: 'Answer',
  timestamp: new Date(),
  metadata: { run_id: run },
});

describe('card action ownership through SSE and retries', () => {
  it.each(['matched', 'wrong_run', 'fallback', 'cancelled'] as const)(
    'keeps %s done metadata on its own answer',
    condition => {
      const before = answer('own', condition === 'wrong_run' ? 'other' : 'current');
      const state = { ...structuredClone(initialChatState), messages: [before] };
      const next = chatReducer(state, {
        type: 'STREAM_DONE',
        payload: {
          messageId: condition === 'fallback' ? 'missing' : 'own',
          metadata: {
            run_id: 'current',
            lia_card_actions: projection,
            ...(condition === 'cancelled' ? { cancelled: true } : {}),
          },
        },
      });
      if (condition === 'matched')
        expect(next.messages[0].metadata?.lia_card_actions).toEqual(projection);
      else expect(next.messages[0].metadata?.lia_card_actions).toBeUndefined();
      expect(state.messages[0]).toEqual(before);
    }
  );

  it.each(['SSE_ERROR', 'STREAM_ERROR'] as const)(
    'preserves the failed selection on %s without borrowing another turn',
    type => {
      const user: Message = {
        id: 'u',
        role: 'user',
        content: 'My reply',
        timestamp: new Date(),
        metadata: { card_composition: selection },
      };
      const state = { ...structuredClone(initialChatState), messages: [user] };
      const next = chatReducer(state, { type, payload: { error: 'Failed' } });
      expect(next.messages.at(-1)?.metadata?.retryCardComposition).toEqual(selection);
      const another: Message = { ...user, id: 'u2', content: 'Unrelated', metadata: {} };
      const later = chatReducer(
        { ...state, messages: [user, another] },
        { type, payload: { error: 'Failed' } }
      );
      expect(later.messages.at(-1)?.metadata?.retryCardComposition).toBeUndefined();
    }
  );
});
