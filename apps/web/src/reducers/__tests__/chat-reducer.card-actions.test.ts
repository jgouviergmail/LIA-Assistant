import { describe, it, expect } from 'vitest';
import { chatReducer } from '../chat-reducer';
import { initialChatState } from '@/types/chat-state';
import type { Message } from '@/types/chat';
import type { CardActionsProjection, CardCompositionWire } from '@/types/card-actions';
import { cardActionsFromMetadata, cardSourceMessageId } from '@/lib/card-actions';

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
            archived_message_id: selection.message_id,
            ...(condition === 'cancelled' ? { cancelled: true } : {}),
          },
        },
      });
      if (condition === 'matched' || condition === 'fallback') {
        expect(next.messages[0].metadata?.lia_card_actions).toEqual(projection);
        expect(cardSourceMessageId(next.messages[0])).toBe(selection.message_id);
        expect(cardActionsFromMetadata(next.messages[0].metadata)).toEqual(projection);
      } else expect(next.messages[0].metadata?.lia_card_actions).toBeUndefined();
      expect(state.messages[0]).toEqual(before);
    }
  );

  it.each(['unknown_run', 'other_run', 'other_row', 'hitl'] as const)(
    'does not give another answer card actions through the %s fallback',
    condition => {
      const before = answer(condition === 'hitl' ? 'hitl_prompt' : 'own');
      before.metadata =
        condition === 'unknown_run'
          ? {}
          : {
              run_id: condition === 'other_run' ? 'previous' : 'current',
              ...(condition === 'other_row'
                ? { message_db_id: '00000000-0000-0000-0000-000000000099' }
                : {}),
            };
      const state = { ...structuredClone(initialChatState), messages: [before] };
      const next = chatReducer(state, {
        type: 'STREAM_DONE',
        payload: {
          messageId: 'missing',
          metadata: {
            run_id: 'current',
            archived_message_id: selection.message_id,
            lia_card_actions: projection,
          },
        },
      });
      expect(next.messages[0].metadata?.lia_card_actions).toBeUndefined();
      if (condition === 'other_row')
        expect(cardSourceMessageId(next.messages[0])).toBe('00000000-0000-0000-0000-000000000099');
      else expect(cardSourceMessageId(next.messages[0])).toBeUndefined();
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
