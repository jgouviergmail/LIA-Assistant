/**
 * chat-reducer — STREAM_DONE fallback token attachment guard (FF2).
 *
 * When STREAM_DONE arrives without a matching message id, token metadata is
 * attached to the LAST assistant message — unless that message is a HITL
 * prompt bubble (ephemeral approval-flow state). Detection is structural
 * (id prefixed "hitl_"), language-agnostic — the previous implementation
 * matched hardcoded French sentences and silently failed in the 5 other
 * UI languages.
 */

import { describe, it, expect } from 'vitest';

import { chatReducer, createInitialState } from '../chat-reducer';
import type { Message } from '@/types/chat';

function stateWithMessages(messages: Message[]) {
  return { ...createInitialState(), messages };
}

function assistantMessage(id: string, content: string): Message {
  return { id, role: 'assistant', content, timestamp: new Date() };
}

const doneAction = {
  type: 'STREAM_DONE',
  payload: {
    messageId: 'missing-id',
    metadata: { tokens_in: 11, tokens_out: 22, cost_eur: 0.01 },
  },
} as const;

describe('chat-reducer — HITL token-attachment guard', () => {
  it('attaches token metadata to the last regular assistant message', () => {
    const state = stateWithMessages([assistantMessage('assistant-1', 'Voici ta réponse.')]);

    const next = chatReducer(state, doneAction as never);

    expect(next.messages[0].tokensIn).toBe(11);
    expect(next.messages[0].tokensOut).toBe(22);
  });

  it('does NOT attach token metadata to a HITL prompt bubble (id prefix)', () => {
    const state = stateWithMessages([
      assistantMessage('hitl_conv1_interrupt-aaa', 'Do you want to send this email as is?'),
    ]);

    const next = chatReducer(state, doneAction as never);

    expect(next.messages[0].tokensIn).toBeUndefined();
    expect(next.messages[0].tokensOut).toBeUndefined();
  });

  it('guard is language-agnostic (English HITL content, hitl_ id)', () => {
    // The former French-content matching would have attached tokens here.
    const state = stateWithMessages([
      assistantMessage('hitl_conv1_interrupt-bbb', 'I will first check your calendar. Confirm?'),
    ]);

    const next = chatReducer(state, doneAction as never);

    expect(next.messages[0].tokensIn).toBeUndefined();
  });
});
