/**
 * chat-reducer — HITL approval-card branch (Lot 1 P1-V1).
 *
 * Transition matrix under test (every arrow has a test):
 *
 *   none ──HITL_AWAITING──▶ awaiting ──HITL_SUBMITTING──▶ submitting
 *   awaiting ──SEND_MESSAGE (typed reply)──▶ resolved(via_text)
 *   submitting ──SEND_MESSAGE (button's own send)──▶ submitting (unchanged)
 *   submitting ──STREAM_DONE──▶ resolved(confirmed|cancelled)
 *   awaiting|submitting ──HITL_EXPIRED──▶ expired
 *   submitting ──STREAM_ERROR (transport)──▶ awaiting (retryable)
 *   any ──HITL_AWAITING──▶ awaiting (last-wins replace)
 *   any ──CLEAR_MESSAGES|HITL_CLEAR──▶ none
 *
 * Invariants: STREAM_DONE without submission never touches an awaiting card
 * (the interrupt stream itself ends WITHOUT done — runtime-proven protocol);
 * input states are deep-frozen to prove immutability.
 */

import { describe, it, expect } from 'vitest';

import { chatReducer } from '@/reducers/chat-reducer';
import { initialChatState, type ChatState } from '@/types/chat-state';
import type { Message } from '@/types/chat';
import type { NormalizedHitlPayload } from '@/types/hitl';
import { deepFreeze } from '@/__tests__/deep-freeze';

function makePayload(overrides: Partial<NormalizedHitlPayload> = {}): NormalizedHitlPayload {
  return {
    messageId: 'hitl_conv_abc',
    kind: 'tool_confirmation',
    actions: [
      { action: 'confirm', label: 'confirm', style: 'primary' },
      { action: 'cancel', label: 'cancel', style: 'destructive' },
    ],
    toolName: 'send_email_tool',
    toolArgs: { to: 'a@b.c' },
    ...overrides,
  };
}

function makeMessage(id: string, role: Message['role'] = 'user'): Message {
  return { id, role, content: `content-${id}`, timestamp: new Date() };
}

function frozenState(overrides: Partial<ChatState> = {}): ChatState {
  return deepFreeze({ ...structuredClone(initialChatState), ...overrides });
}

function awaitingState(payload = makePayload()): ChatState {
  return frozenState({
    hitl: { status: 'awaiting', payload, resolution: null, submittedAction: null },
  });
}

function submittingState(action: 'confirm' | 'cancel' = 'confirm'): ChatState {
  return frozenState({
    hitl: {
      status: 'submitting',
      payload: makePayload(),
      resolution: null,
      submittedAction: action,
    },
  });
}

describe('chatReducer — HITL_AWAITING', () => {
  it('none → awaiting with the normalized payload', () => {
    const payload = makePayload();
    const next = chatReducer(frozenState(), { type: 'HITL_AWAITING', payload: { payload } });

    expect(next.hitl.status).toBe('awaiting');
    expect(next.hitl.payload).toEqual(payload);
    expect(next.hitl.resolution).toBeNull();
    expect(next.hitl.submittedAction).toBeNull();
  });

  it('replaces any previous card (last-wins) including resolved ones', () => {
    const prev = frozenState({
      hitl: {
        status: 'resolved',
        payload: makePayload({ messageId: 'hitl_old' }),
        resolution: 'confirmed',
        submittedAction: 'confirm',
      },
    });
    const fresh = makePayload({ messageId: 'hitl_new' });

    const next = chatReducer(prev, { type: 'HITL_AWAITING', payload: { payload: fresh } });

    expect(next.hitl.status).toBe('awaiting');
    expect(next.hitl.payload?.messageId).toBe('hitl_new');
    expect(next.hitl.resolution).toBeNull();
  });
});

describe('chatReducer — HITL_SUBMITTING', () => {
  it('awaiting → submitting and records the submitted action', () => {
    const next = chatReducer(awaitingState(), {
      type: 'HITL_SUBMITTING',
      payload: { action: 'cancel' },
    });

    expect(next.hitl.status).toBe('submitting');
    expect(next.hitl.submittedAction).toBe('cancel');
  });

  it('is ignored outside awaiting (defensive: double-click after resolve)', () => {
    const state = submittingState('confirm');
    const next = chatReducer(state, { type: 'HITL_SUBMITTING', payload: { action: 'cancel' } });

    expect(next.hitl).toEqual(state.hitl);
  });
});

describe('chatReducer — typed reply while a card is shown', () => {
  it('SEND_MESSAGE while awaiting resolves the card via_text', () => {
    const next = chatReducer(awaitingState(), {
      type: 'SEND_MESSAGE',
      payload: { message: makeMessage('u-1') },
    });

    expect(next.hitl.status).toBe('resolved');
    expect(next.hitl.resolution).toBe('via_text');
  });

  it("SEND_MESSAGE while submitting keeps the submitting state (button's own send)", () => {
    const next = chatReducer(submittingState('confirm'), {
      type: 'SEND_MESSAGE',
      payload: { message: makeMessage('u-2') },
    });

    expect(next.hitl.status).toBe('submitting');
    expect(next.hitl.submittedAction).toBe('confirm');
  });
});

describe('chatReducer — STREAM_DONE', () => {
  // User feedback 2026-07-19: a resolved card must NOT linger — the reply
  // bubble ("OK, c'est annulé.") is the feedback. The turn's done clears
  // submitting (button flow) and resolved (via_text flow) cards entirely.
  it('submitting card is cleared when the resume turn completes', () => {
    const next = chatReducer(submittingState('confirm'), {
      type: 'STREAM_DONE',
      payload: { messageId: 'a-1' },
    });

    expect(next.hitl.status).toBe('none');
    expect(next.hitl.payload).toBeNull();
  });

  it('via_text-resolved card is cleared when the turn completes', () => {
    const resolved = chatReducer(awaitingState(), {
      type: 'SEND_MESSAGE',
      payload: { message: makeMessage('u-x') },
    });
    expect(resolved.hitl.status).toBe('resolved');

    const next = chatReducer(deepFreeze(resolved), {
      type: 'STREAM_DONE',
      payload: { messageId: 'a-2' },
    });

    expect(next.hitl.status).toBe('none');
  });

  it('never touches an awaiting card (interrupt streams end without done)', () => {
    const state = awaitingState();
    const next = chatReducer(state, { type: 'STREAM_DONE', payload: { messageId: 'a-3' } });

    expect(next.hitl).toEqual(state.hitl);
  });

  it('leaves an expired card visible (its turn produced no outcome)', () => {
    const expired = chatReducer(awaitingState(), { type: 'HITL_EXPIRED' });
    const next = chatReducer(deepFreeze(expired), {
      type: 'STREAM_DONE',
      payload: { messageId: 'a-4' },
    });

    expect(next.hitl.status).toBe('expired');
  });
});

describe('chatReducer — expired card lifecycle', () => {
  it('SEND_MESSAGE clears an expired card (user moved on)', () => {
    const expired = chatReducer(awaitingState(), { type: 'HITL_EXPIRED' });
    const next = chatReducer(deepFreeze(expired), {
      type: 'SEND_MESSAGE',
      payload: { message: makeMessage('u-x') },
    });

    expect(next.hitl.status).toBe('none');
  });
});

describe('chatReducer — HITL_EXPIRED', () => {
  it('awaiting → expired', () => {
    const next = chatReducer(awaitingState(), { type: 'HITL_EXPIRED' });
    expect(next.hitl.status).toBe('expired');
  });

  it('submitting → expired', () => {
    const next = chatReducer(submittingState(), { type: 'HITL_EXPIRED' });
    expect(next.hitl.status).toBe('expired');
  });

  it('is ignored when no card is shown', () => {
    const next = chatReducer(frozenState(), { type: 'HITL_EXPIRED' });
    expect(next.hitl.status).toBe('none');
  });
});

describe('chatReducer — transport error while submitting', () => {
  it('STREAM_ERROR returns the card to awaiting (retryable)', () => {
    const next = chatReducer(submittingState('confirm'), {
      type: 'STREAM_ERROR',
      payload: { error: 'network hiccup' },
    });

    expect(next.hitl.status).toBe('awaiting');
    expect(next.hitl.submittedAction).toBeNull();
  });

  it('STREAM_ERROR leaves an awaiting card untouched', () => {
    const state = awaitingState();
    const next = chatReducer(state, { type: 'STREAM_ERROR', payload: { error: 'boom' } });

    expect(next.hitl).toEqual(state.hitl);
  });
});

describe('chatReducer — resets', () => {
  it('CLEAR_MESSAGES resets the card to none', () => {
    const next = chatReducer(awaitingState(), { type: 'CLEAR_MESSAGES' });
    expect(next.hitl.status).toBe('none');
    expect(next.hitl.payload).toBeNull();
  });

  it('HITL_CLEAR resets from any state', () => {
    const next = chatReducer(submittingState(), { type: 'HITL_CLEAR' });
    expect(next.hitl.status).toBe('none');
  });
});
