/**
 * Reducer tests for compaction v2 state transitions (Task 3.1).
 *
 * Verifies that the `STREAM_COMPACTION_START` / `STREAM_COMPACTION_DONE`
 * actions drive the chat status correctly and that the `compaction` field
 * carries the right phase/strategy. The legacy reducer had no test harness;
 * this file scaffolds it for the compaction-v2 work.
 */

import { describe, it, expect } from 'vitest';

import { chatReducer } from '@/reducers/chat-reducer';
import { initialChatState, type ChatState } from '@/types/chat-state';

const baseState: ChatState = { ...initialChatState };

describe('chatReducer — compaction v2 transitions', () => {
  it('moves to "compacting" on STREAM_COMPACTION_START and records metadata', () => {
    const next = chatReducer(baseState, {
      type: 'STREAM_COMPACTION_START',
      payload: { estimatedDurationSeconds: 30 },
    });

    expect(next.status).toBe('compacting');
    expect(next.compaction?.phase).toBe('in_progress');
    expect(next.compaction?.estimatedDurationSeconds).toBe(30);
    expect(next.compaction?.startedAt).toBeTypeOf('number');
  });

  it('returns to "streaming" on STREAM_COMPACTION_DONE after a start', () => {
    let s = chatReducer(baseState, {
      type: 'STREAM_COMPACTION_START',
      payload: {},
    });
    s = chatReducer(s, {
      type: 'STREAM_COMPACTION_DONE',
      payload: {
        tokensSaved: 5000,
        durationMs: 12000,
        strategy: 'multi_chunk',
      },
    });

    expect(s.status).toBe('streaming');
    expect(s.compaction?.phase).toBe('done');
    expect(s.compaction?.tokensSaved).toBe(5000);
    expect(s.compaction?.durationMs).toBe(12000);
    expect(s.compaction?.strategy).toBe('multi_chunk');
  });

  it('marks phase="truncated" when strategy is "truncation"', () => {
    let s = chatReducer(baseState, {
      type: 'STREAM_COMPACTION_START',
      payload: {},
    });
    s = chatReducer(s, {
      type: 'STREAM_COMPACTION_DONE',
      payload: { strategy: 'truncation' },
    });

    expect(s.compaction?.phase).toBe('truncated');
  });

  it('STREAM_COMPACTION_DONE without prior START does not force status to "streaming"', () => {
    // Defensive: a late DONE event arriving while the chat is "idle" must
    // not override the status. We still record the compaction metadata so
    // the UI can show the truncation banner if applicable.
    const s = chatReducer(baseState, {
      type: 'STREAM_COMPACTION_DONE',
      payload: { strategy: 'single_chunk', tokensSaved: 100 },
    });

    expect(s.status).toBe('idle');
    expect(s.compaction?.phase).toBe('done');
  });

  it('SEND_MESSAGE clears any previous compaction banner', () => {
    let s = chatReducer(baseState, {
      type: 'STREAM_COMPACTION_DONE',
      payload: { strategy: 'truncation' },
    });
    expect(s.compaction?.phase).toBe('truncated');

    s = chatReducer(s, {
      type: 'SEND_MESSAGE',
      payload: {
        message: {
          id: 'msg-1',
          role: 'user',
          content: 'next turn',
          timestamp: new Date(),
        },
      },
    });

    expect(s.compaction).toBeNull();
  });

  it('CLEAR_MESSAGES resets the compaction state to null', () => {
    let s = chatReducer(baseState, {
      type: 'STREAM_COMPACTION_START',
      payload: {},
    });
    expect(s.compaction?.phase).toBe('in_progress');

    s = chatReducer(s, { type: 'CLEAR_MESSAGES' });
    expect(s.compaction).toBeNull();
  });
});
