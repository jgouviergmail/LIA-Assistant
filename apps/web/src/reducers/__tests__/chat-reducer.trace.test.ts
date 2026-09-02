/**
 * chat-reducer — TRACE_ATTACH (Lot 2 P2-V1, execution trace).
 *
 * Attaches the captured backstage record to the matching assistant message.
 * Invariants: targets by id, no-op on unknown id, replaces a prior trace
 * (idempotent re-attach), caps retained steps, and leaves every other slice
 * untouched. Input states are deep-frozen to prove immutability.
 */

import { describe, it, expect } from 'vitest';

import { chatReducer } from '@/reducers/chat-reducer';
import { initialChatState, type ChatState } from '@/types/chat-state';
import type { Message } from '@/types/chat';
import type { ExecutionTrace, ExecutionTraceStep } from '@/types/execution-trace';
import { MAX_TRACE_STEPS, TRACE_HEAD_KEEP } from '@/types/execution-trace';
import { deepFreeze } from '@/__tests__/deep-freeze';

function step(label: string): ExecutionTraceStep {
  return { emoji: '⚙️', label, category: 'system' };
}

function trace(overrides: Partial<ExecutionTrace> = {}): ExecutionTrace {
  return {
    steps: [step('router'), step('planner')],
    reasoning: '',
    durationMs: 1200,
    ...overrides,
  };
}

function assistant(id: string): Message {
  return { id, role: 'assistant', content: 'answer', timestamp: new Date() };
}

function frozenState(messages: Message[]): ChatState {
  return deepFreeze({ ...structuredClone(initialChatState), messages });
}

describe('chatReducer — TRACE_ATTACH', () => {
  it('attaches the trace to the message with the matching id', () => {
    const state = frozenState([assistant('a-1')]);
    const t = trace();

    const next = chatReducer(state, {
      type: 'TRACE_ATTACH',
      payload: { messageId: 'a-1', trace: t },
    });

    expect(next.messages[0].executionTrace).toEqual(t);
  });

  it('is a no-op when no message matches the id', () => {
    const state = frozenState([assistant('a-1')]);

    const next = chatReducer(state, {
      type: 'TRACE_ATTACH',
      payload: { messageId: 'ghost', trace: trace() },
    });

    expect(next.messages[0].executionTrace).toBeUndefined();
    expect(next.messages).toEqual(state.messages);
  });

  it('replaces a previously attached trace (idempotent re-attach)', () => {
    const withTrace: Message = { ...assistant('a-1'), executionTrace: trace({ durationMs: 1 }) };
    const state = frozenState([withTrace]);
    const fresh = trace({ durationMs: 9999 });

    const next = chatReducer(state, {
      type: 'TRACE_ATTACH',
      payload: { messageId: 'a-1', trace: fresh },
    });

    expect(next.messages[0].executionTrace?.durationMs).toBe(9999);
  });

  it('caps retained steps at MAX_TRACE_STEPS keeping head AND tail, and counts the omission', () => {
    // Lot C (2026-09): tail-only retention silently erased the turn's FIRST
    // actions — the ones an injected instruction would have triggered. The cap
    // now keeps the opening acts (head) plus the most recent ones (tail), and
    // states the exact number omitted (a shown count is a claim: exact or absent).
    const state = frozenState([assistant('a-1')]);
    const many = Array.from({ length: MAX_TRACE_STEPS + 25 }, (_, i) => step(`s${i}`));

    const next = chatReducer(state, {
      type: 'TRACE_ATTACH',
      payload: { messageId: 'a-1', trace: trace({ steps: many }) },
    });

    const attached = next.messages[0].executionTrace!;
    expect(attached.steps).toHaveLength(MAX_TRACE_STEPS);
    // The head is retained: the very first steps stay visible.
    expect(attached.steps[0].label).toBe('s0');
    expect(attached.steps[TRACE_HEAD_KEEP - 1].label).toBe(`s${TRACE_HEAD_KEEP - 1}`);
    // The tail is retained (most informative for "what did it just do").
    expect(attached.steps[attached.steps.length - 1].label).toBe(`s${MAX_TRACE_STEPS + 24}`);
    // The gap is stated exactly.
    expect(attached.omittedSteps).toBe(25);
  });

  it('sets no omission count when the steps fit the cap', () => {
    const state = frozenState([assistant('a-1')]);
    const exact = Array.from({ length: MAX_TRACE_STEPS }, (_, i) => step(`s${i}`));

    const next = chatReducer(state, {
      type: 'TRACE_ATTACH',
      payload: { messageId: 'a-1', trace: trace({ steps: exact }) },
    });

    const attached = next.messages[0].executionTrace!;
    expect(attached.steps).toHaveLength(MAX_TRACE_STEPS);
    expect(attached.steps[0].label).toBe('s0');
    expect(attached.omittedSteps).toBeUndefined();
  });

  it('leaves other messages and slices untouched', () => {
    const state = frozenState([assistant('a-1'), assistant('a-2')]);

    const next = chatReducer(state, {
      type: 'TRACE_ATTACH',
      payload: { messageId: 'a-2', trace: trace() },
    });

    expect(next.messages[0].executionTrace).toBeUndefined();
    expect(next.messages[1].executionTrace).toBeDefined();
    expect(next.status).toBe(state.status);
    expect(next.hitl).toEqual(state.hitl);
  });
});
