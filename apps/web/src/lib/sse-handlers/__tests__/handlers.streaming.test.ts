/**
 * sse-handlers — token streaming, post-processed replacement and stream
 * completion (including the Psyche Engine store push on `done`).
 *
 * Token BATCHING (rAF coalescing in processSSEChunk) is covered by
 * token-batching.test.ts; this suite exercises the handlers directly.
 */

import { describe, it, expect, beforeEach } from 'vitest';

import { handleToken, handleContentReplacement, handleDone } from '@/lib/sse-handlers/handlers';
import { usePsycheStore } from '@/stores/psycheStore';
import type { ChatStreamChunk } from '@/types/chat';
import { buildHandlerContext, dispatchedOfType } from './context-fixture';

function tokenChunk(content: string): ChatStreamChunk {
  return { type: 'token', content } as ChatStreamChunk;
}

describe('handleToken', () => {
  it('replaces the progress message with the first real token and closes the progress phase', () => {
    const { context, dispatch, state } = buildHandlerContext({
      progressMessageId: 'assistant-1',
    });
    context.executionStepsRef.current = ['*step*'];
    context.emittedStepKeysRef.current = new Set(['k']);
    context.reasoningBufRef.current = 'thinking…';

    handleToken(tokenChunk('Hello'), context);

    expect(dispatchedOfType(dispatch, 'STREAM_REPLACE')).toEqual([
      { content: 'Hello', phase: 'answer' },
    ]);
    expect(context.executionStepsRef.current).toEqual([]);
    expect(context.emittedStepKeysRef.current.size).toBe(0);
    expect(context.reasoningBufRef.current).toBe('');
    expect(state.normalStreamInitialized).toBe(true);
    expect(state.progressMessageId).toBeNull();
  });

  it('starts a fresh stream when no progress message exists (backwards compatible)', () => {
    const { context, dispatch, state } = buildHandlerContext();

    handleToken(tokenChunk('Hi'), context);

    expect(dispatchedOfType(dispatch, 'STREAM_START')).toEqual([
      { messageId: 'assistant-1', phase: 'answer' },
    ]);
    expect(dispatchedOfType(dispatch, 'STREAM_TOKEN')).toEqual([{ token: 'Hi' }]);
    expect(state.normalStreamInitialized).toBe(true);
  });

  it('appends subsequent tokens once the stream is initialized', () => {
    const { context, dispatch } = buildHandlerContext({ normalStreamInitialized: true });

    handleToken(tokenChunk(' world'), context);

    expect(dispatch).toHaveBeenCalledTimes(1);
    expect(dispatchedOfType(dispatch, 'STREAM_TOKEN')).toEqual([{ token: ' world' }]);
  });
});

describe('handleContentReplacement', () => {
  const replacementChunk = {
    type: 'content_replacement',
    content: '<div class="card">final html</div>',
  } as ChatStreamChunk;

  it('creates the message container first when tokens were skipped (ReAct/HTML cards)', () => {
    const { context, dispatch, state } = buildHandlerContext({
      progressMessageId: 'assistant-1',
    });
    context.executionStepsRef.current = ['*step*'];
    context.reasoningBufRef.current = 'buf';

    handleContentReplacement(replacementChunk, context);

    expect(dispatchedOfType(dispatch, 'STREAM_START')).toEqual([
      { messageId: 'assistant-1', phase: 'answer' },
    ]);
    expect(dispatchedOfType(dispatch, 'STREAM_REPLACE')).toEqual([
      { content: '<div class="card">final html</div>', phase: 'answer' },
    ]);
    expect(context.executionStepsRef.current).toEqual([]);
    expect(context.reasoningBufRef.current).toBe('');
    expect(state.normalStreamInitialized).toBe(true);
    expect(state.progressMessageId).toBeNull();
  });

  it('replaces directly when the stream is already initialized', () => {
    const { context, dispatch } = buildHandlerContext({ normalStreamInitialized: true });

    handleContentReplacement(replacementChunk, context);

    expect(dispatchedOfType(dispatch, 'STREAM_START')).toHaveLength(0);
    expect(dispatchedOfType(dispatch, 'STREAM_REPLACE')).toHaveLength(1);
  });

  it('keeps a null progressMessageId untouched while initializing', () => {
    const { context, dispatch, state } = buildHandlerContext();

    handleContentReplacement(replacementChunk, context);

    expect(dispatchedOfType(dispatch, 'STREAM_START')).toHaveLength(1);
    expect(state.progressMessageId).toBeNull();
  });
});

describe('handleDone', () => {
  beforeEach(() => {
    usePsycheStore.getState().reset();
  });

  it('dispatches STREAM_DONE with the assistant message id and metadata', () => {
    const { context, dispatch } = buildHandlerContext();
    const metadata = { tokens_in: 10, tokens_out: 5 };

    handleDone({ type: 'done', content: '', metadata } as ChatStreamChunk, context);

    expect(dispatchedOfType(dispatch, 'STREAM_DONE')).toEqual([
      { messageId: 'assistant-1', metadata },
    ]);
  });

  it('pushes the psyche_state snapshot into the Zustand store', () => {
    const { context } = buildHandlerContext();
    const psyche = {
      mood_label: 'playful',
      mood_color: '#22c55e',
      mood_pleasure: 0.8,
      mood_arousal: 0.3,
      mood_dominance: 0.6,
      active_emotion: 'joy',
      emotion_intensity: 0.9,
      relationship_stage: 'EXPLORATORY',
    };

    handleDone(
      { type: 'done', content: '', metadata: { psyche_state: psyche } } as ChatStreamChunk,
      context
    );

    const store = usePsycheStore.getState();
    expect(store.moodLabel).toBe('playful');
    expect(store.moodColor).toBe('#22c55e');
    expect(store.activeEmotion).toBe('joy');
    expect(store.relationshipStage).toBe('EXPLORATORY');
  });

  it('leaves the psyche store untouched when metadata has no psyche_state', () => {
    const { context } = buildHandlerContext();

    handleDone({ type: 'done', content: '', metadata: {} } as ChatStreamChunk, context);

    expect(usePsycheStore.getState().moodLabel).toBe('neutral');
  });

  it('tolerates a missing metadata object entirely', () => {
    const { context, dispatch } = buildHandlerContext();

    handleDone({ type: 'done', content: '' } as ChatStreamChunk, context);

    expect(dispatchedOfType(dispatch, 'STREAM_DONE')).toEqual([
      { messageId: 'assistant-1', metadata: undefined },
    ]);
  });
});
