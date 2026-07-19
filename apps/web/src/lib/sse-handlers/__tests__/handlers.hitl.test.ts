/**
 * sse-handlers — HITL streaming pipeline.
 *
 * Covers the 3-step streaming flow (hitl_interrupt_metadata →
 * hitl_question_token → hitl_interrupt_complete) with its buffering and
 * fallback ladder (buffer → generated_question → i18n template), plus the
 * legacy non-streaming hitl_interrupt handler.
 */

import { describe, it, expect, vi } from 'vitest';

import {
  handleHitlInterruptMetadata,
  handleHitlQuestionToken,
  handleHitlInterruptComplete,
  handleHitlInterruptLegacy,
  handleHitlStreamingFallback,
  handleError,
} from '@/lib/sse-handlers/handlers';
import { logger } from '@/lib/logger';
import type { ChatStreamChunk } from '@/types/chat';
import { buildHandlerContext, dispatchedOfType } from './context-fixture';

vi.mock('@/lib/logger', () => ({
  logger: { debug: vi.fn(), info: vi.fn(), warn: vi.fn(), error: vi.fn() },
}));

const ACTION_REQUESTS = [{ name: 'delete_event_tool', args: { event_id: 'evt_1' } }];

function metadataChunk(messageId?: string): ChatStreamChunk {
  return {
    type: 'hitl_interrupt_metadata',
    content: '',
    metadata: {
      ...(messageId ? { message_id: messageId } : {}),
      action_requests: ACTION_REQUESTS,
    },
  } as ChatStreamChunk;
}

function questionTokenChunk(messageId: string | undefined, token: string): ChatStreamChunk {
  return {
    type: 'hitl_question_token',
    content: token,
    metadata: { message_id: messageId },
  } as ChatStreamChunk;
}

function completeChunk(messageId: string, extra: Record<string, unknown> = {}): ChatStreamChunk {
  return {
    type: 'hitl_interrupt_complete',
    content: '',
    metadata: { message_id: messageId, action_requests: ACTION_REQUESTS, ...extra },
  } as ChatStreamChunk;
}

describe('handleHitlInterruptMetadata', () => {
  it('initializes the question buffer and morphs the existing progress message', () => {
    const { context, dispatch } = buildHandlerContext({ progressMessageId: 'assistant-1' });
    context.executionStepsRef.current = ['*step*'];
    context.emittedStepKeysRef.current = new Set(['k']);

    handleHitlInterruptMetadata(metadataChunk('hitl_msg_1'), context);

    expect(context.hitlQuestionBuffer.current.get('hitl_msg_1')).toBe('');
    expect(context.executionStepsRef.current).toEqual([]);
    expect(context.emittedStepKeysRef.current.size).toBe(0);
    expect(dispatchedOfType(dispatch, 'STREAM_REPLACE')).toEqual([
      { content: 'hitl.validating_access', phase: 'progress' },
    ]);
  });

  it('creates the message when no progress message exists (edge case)', () => {
    const { context, dispatch, state } = buildHandlerContext();

    handleHitlInterruptMetadata(metadataChunk('hitl_msg_1'), context);

    expect(dispatchedOfType(dispatch, 'STREAM_START')).toEqual([
      { messageId: 'hitl_msg_1', initialContent: 'hitl.validating_access', phase: 'progress' },
    ]);
    expect(state.progressMessageId).toBe('hitl_msg_1');
  });

  it('generates a hitl_-prefixed fallback id when the backend omits message_id', () => {
    const { context } = buildHandlerContext({ progressMessageId: 'assistant-1' });

    handleHitlInterruptMetadata(metadataChunk(undefined), context);

    const bufferedIds = [...context.hitlQuestionBuffer.current.keys()];
    expect(bufferedIds).toHaveLength(1);
    expect(bufferedIds[0]).toMatch(/^hitl_/);
  });
});

describe('handleHitlQuestionToken', () => {
  it('replaces the placeholder with the first token, then appends', () => {
    const { context, dispatch } = buildHandlerContext();
    context.hitlQuestionBuffer.current.set('hitl_msg_1', '');

    handleHitlQuestionToken(questionTokenChunk('hitl_msg_1', 'Do '), context);
    handleHitlQuestionToken(questionTokenChunk('hitl_msg_1', 'you confirm?'), context);

    expect(dispatchedOfType(dispatch, 'STREAM_REPLACE')).toEqual([
      { content: 'Do ', phase: 'answer' },
    ]);
    expect(dispatchedOfType(dispatch, 'STREAM_TOKEN')).toEqual([{ token: 'you confirm?' }]);
    expect(context.hitlQuestionBuffer.current.get('hitl_msg_1')).toBe('Do you confirm?');
  });

  it('preserves whitespace-only tokens (word separators)', () => {
    const { context, dispatch } = buildHandlerContext();
    context.hitlQuestionBuffer.current.set('hitl_msg_1', 'word');

    handleHitlQuestionToken(questionTokenChunk('hitl_msg_1', ' '), context);

    expect(dispatchedOfType(dispatch, 'STREAM_TOKEN')).toEqual([{ token: ' ' }]);
  });

  it('ignores empty tokens and tokens without a message id', () => {
    const { context, dispatch } = buildHandlerContext();

    handleHitlQuestionToken(questionTokenChunk('hitl_msg_1', ''), context);
    handleHitlQuestionToken(questionTokenChunk(undefined, 'orphan'), context);

    expect(dispatch).not.toHaveBeenCalled();
  });
});

describe('handleHitlInterruptComplete', () => {
  it('finalizes with the buffered question: STREAM_DONE without token metadata, buffer cleaned', () => {
    const { context, dispatch } = buildHandlerContext();
    context.hitlQuestionBuffer.current.set('hitl_msg_1', 'Do you confirm the deletion?');

    handleHitlInterruptComplete(completeChunk('hitl_msg_1'), context);

    // The streamed question is already displayed — no extra token dispatch.
    expect(dispatchedOfType(dispatch, 'STREAM_TOKEN')).toHaveLength(0);
    expect(dispatchedOfType(dispatch, 'STREAM_DONE')).toEqual([
      { messageId: 'hitl_msg_1', metadata: {} },
    ]);
    expect(context.hitlQuestionBuffer.current.has('hitl_msg_1')).toBe(false);
  });

  it('falls back to metadata.generated_question when the buffer is empty', () => {
    const { context, dispatch } = buildHandlerContext();
    context.hitlQuestionBuffer.current.set('hitl_msg_1', '');

    handleHitlInterruptComplete(
      completeChunk('hitl_msg_1', { generated_question: 'Generated fallback question?' }),
      context
    );

    expect(dispatchedOfType(dispatch, 'STREAM_TOKEN')).toEqual([
      { token: 'Generated fallback question?' },
    ]);
    expect(dispatchedOfType(dispatch, 'STREAM_DONE')).toHaveLength(1);
  });

  it('falls back to the i18n template question as a last resort', () => {
    const { context, dispatch } = buildHandlerContext();

    handleHitlInterruptComplete(completeChunk('hitl_msg_1'), context);

    const tokens = dispatchedOfType(dispatch, 'STREAM_TOKEN') as Array<{ token: string }>;
    expect(tokens).toHaveLength(1);
    // generateFallbackHitlQuestion resolves through i18n — with the key-echo
    // t we assert the delete-category template key is used.
    expect(tokens[0].token).toContain('hitl.delete');
    expect(dispatchedOfType(dispatch, 'STREAM_DONE')).toHaveLength(1);
  });
});

describe('handleHitlStreamingFallback', () => {
  it('surfaces the degraded HITL streaming as a structured warning (awareness event)', () => {
    // The backend emits this when the LLM stream for the HITL question fails
    // and it falls back to a template — the regular hitl_question_token
    // chunks that follow carry the fallback question, so no dispatch here.
    const { context, dispatch } = buildHandlerContext();

    handleHitlStreamingFallback(
      {
        type: 'hitl_streaming_fallback',
        content: '',
        metadata: { message_id: 'hitl_1', error: 'streaming_failed', error_type: 'TimeoutError' },
      } as ChatStreamChunk,
      context
    );

    expect(dispatch).not.toHaveBeenCalled();
    expect(logger.warn).toHaveBeenCalledWith(
      'chat_hitl_streaming_fallback',
      expect.objectContaining({ message_id: 'hitl_1', error_type: 'TimeoutError' })
    );
  });
});

describe('handleHitlInterruptLegacy', () => {
  it('renders the pre-generated question as a full START/TOKEN/DONE sequence', () => {
    const { context, dispatch } = buildHandlerContext();

    handleHitlInterruptLegacy(
      {
        type: 'hitl_interrupt',
        content: '',
        metadata: { generated_question: 'Legacy question?', action_requests: ACTION_REQUESTS },
      } as ChatStreamChunk,
      context
    );

    const starts = dispatchedOfType(dispatch, 'STREAM_START') as Array<{ messageId: string }>;
    expect(starts).toHaveLength(1);
    expect(starts[0].messageId).toMatch(/^hitl_/);
    expect(dispatchedOfType(dispatch, 'STREAM_TOKEN')).toEqual([{ token: 'Legacy question?' }]);
    const dones = dispatchedOfType(dispatch, 'STREAM_DONE') as Array<{ messageId: string }>;
    expect(dones[0].messageId).toBe(starts[0].messageId);
  });

  it('falls back to the i18n template when no question was generated', () => {
    const { context, dispatch } = buildHandlerContext();

    handleHitlInterruptLegacy(
      {
        type: 'hitl_interrupt',
        content: '',
        metadata: { action_requests: ACTION_REQUESTS },
      } as ChatStreamChunk,
      context
    );

    const tokens = dispatchedOfType(dispatch, 'STREAM_TOKEN') as Array<{ token: string }>;
    expect(tokens[0].token).toContain('hitl.delete');
  });

  it('survives metadata without action_requests (empty-list fallback)', () => {
    const { context, dispatch } = buildHandlerContext();

    handleHitlInterruptLegacy(
      { type: 'hitl_interrupt', content: '', metadata: {} } as ChatStreamChunk,
      context
    );

    const tokens = dispatchedOfType(dispatch, 'STREAM_TOKEN') as Array<{ token: string }>;
    expect(tokens[0].token).toBe('hitl.default');
  });
});

describe('handleHitlInterruptMetadata — approval card (Lot 1 P1-V1)', () => {
  it('dispatches HITL_AWAITING with the normalized payload for a card-kind interrupt', () => {
    const { context, dispatch } = buildHandlerContext({ progressMessageId: 'assistant-1' });
    const chunk = {
      type: 'hitl_interrupt_metadata',
      content: '',
      metadata: {
        message_id: 'hitl_card_1',
        action_requests: [
          { type: 'tool_confirmation', tool_name: 'send_email_tool', tool_args: { to: 'a@b.c' } },
        ],
      },
    } as ChatStreamChunk;

    handleHitlInterruptMetadata(chunk, context);

    const awaiting = dispatchedOfType(dispatch, 'HITL_AWAITING') as Array<{
      payload: { kind: string; messageId: string };
    }>;
    expect(awaiting).toHaveLength(1);
    expect(awaiting[0].payload).toMatchObject({
      kind: 'tool_confirmation',
      messageId: 'hitl_card_1',
    });
  });
});

describe('handleError — stale HITL decision (Lot 1 P1-V1)', () => {
  it('flips the card to expired on error_code hitl_decision_stale before STREAM_ERROR', () => {
    const { context, dispatch } = buildHandlerContext();
    const chunk = {
      type: 'error',
      content: 'Cette demande n’est plus active.',
      metadata: { error_code: 'hitl_decision_stale' },
    } as ChatStreamChunk;

    handleError(chunk, context);

    const types = dispatch.mock.calls.map(c => c[0].type);
    expect(types).toContain('HITL_EXPIRED');
    expect(types).toContain('STREAM_ERROR');
    // HITL_EXPIRED must precede STREAM_ERROR (the retry branch must not re-arm).
    expect(types.indexOf('HITL_EXPIRED')).toBeLessThan(types.indexOf('STREAM_ERROR'));
  });

  it('does not flip the card for a generic error', () => {
    const { context, dispatch } = buildHandlerContext();
    const chunk = {
      type: 'error',
      content: 'Boom',
      metadata: { error_code: 'internal_error' },
    } as ChatStreamChunk;

    handleError(chunk, context);

    expect(dispatchedOfType(dispatch, 'HITL_EXPIRED')).toHaveLength(0);
  });
});
