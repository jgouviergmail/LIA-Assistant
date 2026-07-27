/**
 * Error bubbles carry what it takes to retry (W3).
 *
 * A failed turn used to end as a plain assistant bubble holding the localized
 * error text and nothing else: no marker, no way back. The user had to find
 * their question again and retype it — the failure was a dead end, on the one
 * surface where recovery matters most.
 *
 * The reducer now marks those bubbles and pins the prompt that produced them,
 * so the retry replays EXACTLY what was asked rather than whatever happens to
 * be the latest user message when the button is pressed.
 */

import { describe, it, expect } from 'vitest';

import { chatReducer } from '@/reducers/chat-reducer';
import { initialChatState, type ChatState } from '@/types/chat-state';
import type { Message } from '@/types/chat';

function userMessage(id: string, content: string): Message {
  return { id, role: 'user', content, timestamp: new Date() };
}

function assistantMessage(id: string, content: string): Message {
  return { id, role: 'assistant', content, timestamp: new Date() };
}

function stateWith(messages: Message[]): ChatState {
  return { ...structuredClone(initialChatState), messages };
}

describe.each(['SSE_ERROR', 'STREAM_ERROR'] as const)('%s — retry affordance', actionType => {
  it('marks the error bubble so the UI can offer a way back', () => {
    const next = chatReducer(stateWith([userMessage('u1', 'Quelle météo demain ?')]), {
      type: actionType,
      payload: { error: 'Connexion perdue.' },
    });

    const bubble = next.messages.at(-1);
    expect(bubble?.role).toBe('assistant');
    expect(bubble?.content).toBe('Connexion perdue.');
    expect(bubble?.metadata?.type).toBe('error');
  });

  it('pins the prompt that failed, not the latest user text', () => {
    // Two turns: the retry must replay the SECOND question, the one that broke.
    const next = chatReducer(
      stateWith([
        userMessage('u1', 'Première question'),
        assistantMessage('a1', 'Première réponse'),
        userMessage('u2', 'Deuxième question'),
      ]),
      { type: actionType, payload: { error: 'boom' } }
    );

    expect(next.messages.at(-1)?.metadata?.retryPrompt).toBe('Deuxième question');
  });

  it('offers no retry when no user message preceded the failure', () => {
    // A proactive turn can fail without any question behind it; offering
    // "retry" there would replay nothing.
    const next = chatReducer(stateWith([assistantMessage('a1', 'Rappel')]), {
      type: actionType,
      payload: { error: 'boom' },
    });

    expect(next.messages.at(-1)?.metadata?.retryPrompt).toBeUndefined();
  });

  it('ignores an empty user message as a retry source', () => {
    const next = chatReducer(stateWith([userMessage('u1', '   ')]), {
      type: actionType,
      payload: { error: 'boom' },
    });

    expect(next.messages.at(-1)?.metadata?.retryPrompt).toBeUndefined();
  });

  it('leaves the earlier conversation untouched', () => {
    const before = [userMessage('u1', 'Question'), assistantMessage('a1', 'Réponse')];
    const next = chatReducer(stateWith(before), {
      type: actionType,
      payload: { error: 'boom' },
    });

    expect(next.messages.slice(0, 2)).toEqual(before);
    expect(next.messages).toHaveLength(3);
  });

  it('still reports the error status', () => {
    const next = chatReducer(stateWith([userMessage('u1', 'Question')]), {
      type: actionType,
      payload: { error: 'boom' },
    });

    expect(next.status).toBe('error');
    expect(next.streaming.sseStatus).toBe('error');
  });
});

describe('STREAM_ERROR — existing HITL behaviour is preserved', () => {
  it('re-arms a submitting card (transport failure is retryable)', () => {
    const state: ChatState = {
      ...structuredClone(initialChatState),
      messages: [userMessage('u1', 'Envoie le mail')],
      hitl: {
        status: 'submitting',
        payload: null,
        resolution: null,
        submittedAction: 'confirm',
      },
    };

    const next = chatReducer(state, { type: 'STREAM_ERROR', payload: { error: 'boom' } });

    expect(next.hitl.status).toBe('awaiting');
    expect(next.hitl.submittedAction).toBeNull();
  });
});
