/**
 * chat-reducer — streaming.phase transitions (progress steps vs answer).
 *
 * The phase drives the execution-steps styling and the streaming caret in
 * ChatMessage: 'progress' while the active message shows accumulated step
 * lines, 'answer' once real tokens replace them.
 */

import { describe, it, expect } from 'vitest';

import { chatReducer } from '@/reducers/chat-reducer';
import { initialChatState, type ChatState } from '@/types/chat-state';
import { deepFreeze } from '@/__tests__/deep-freeze';

function frozenState(overrides: Partial<ChatState> = {}): ChatState {
  return deepFreeze({ ...structuredClone(initialChatState), ...overrides });
}

describe('chatReducer — streaming.phase', () => {
  it('starts in the answer phase', () => {
    expect(initialChatState.streaming.phase).toBe('answer');
  });

  it('STREAM_START with phase progress enters the progress phase', () => {
    const next = chatReducer(frozenState(), {
      type: 'STREAM_START',
      payload: { messageId: 'a-1', initialContent: '*📋 step*', phase: 'progress' },
    });
    expect(next.streaming.phase).toBe('progress');
  });

  it('STREAM_REPLACE without phase preserves the current phase', () => {
    const progress = chatReducer(frozenState(), {
      type: 'STREAM_START',
      payload: { messageId: 'a-1', initialContent: '*📋 step*', phase: 'progress' },
    });
    const next = chatReducer(deepFreeze(progress), {
      type: 'STREAM_REPLACE',
      payload: { content: '*📋 step*\n*📅 step 2*' },
    });
    expect(next.streaming.phase).toBe('progress');
  });

  it('STREAM_REPLACE with phase answer flips to the answer phase (first token)', () => {
    const progress = chatReducer(frozenState(), {
      type: 'STREAM_START',
      payload: { messageId: 'a-1', initialContent: '*📋 step*', phase: 'progress' },
    });
    const next = chatReducer(deepFreeze(progress), {
      type: 'STREAM_REPLACE',
      payload: { content: 'Hello', phase: 'answer' },
    });
    expect(next.streaming.phase).toBe('answer');
  });

  it('idempotent STREAM_START on an existing message updates the phase', () => {
    const progress = chatReducer(frozenState(), {
      type: 'STREAM_START',
      payload: { messageId: 'a-1', initialContent: '*📋 step*', phase: 'progress' },
    });
    const next = chatReducer(deepFreeze(progress), {
      type: 'STREAM_START',
      payload: { messageId: 'a-1', phase: 'answer' },
    });
    expect(next.streaming.phase).toBe('answer');
    expect(next.messages).toHaveLength(1);
  });

  it('STREAM_DONE resets the phase to answer', () => {
    const progress = chatReducer(frozenState(), {
      type: 'STREAM_START',
      payload: { messageId: 'a-1', initialContent: '*📋 step*', phase: 'progress' },
    });
    const next = chatReducer(deepFreeze(progress), {
      type: 'STREAM_DONE',
      payload: { messageId: 'a-1' },
    });
    expect(next.streaming.phase).toBe('answer');
  });

  it('SSE_DISCONNECTED resets the phase to answer', () => {
    const progress = chatReducer(frozenState(), {
      type: 'STREAM_START',
      payload: { messageId: 'a-1', initialContent: '*📋 step*', phase: 'progress' },
    });
    const next = chatReducer(deepFreeze(progress), { type: 'SSE_DISCONNECTED' });
    expect(next.streaming.phase).toBe('answer');
  });
});
