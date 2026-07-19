/**
 * SSE handler tests for compaction v2 events (Task 3.2).
 *
 * Verifies that `execution_step` chunks carrying `metadata.step_type ===
 * 'compaction'` are intercepted by `handleExecutionStep` and translated to
 * `STREAM_COMPACTION_START` / `STREAM_COMPACTION_DONE` dispatches, instead of
 * being accumulated into the generic progress feedback message.
 */

import { describe, it, expect, vi } from 'vitest';

import { handleExecutionStep } from '@/lib/sse-handlers/handlers';
import type { SSEHandlerContext } from '@/lib/sse-handlers/types';
import type { ChatStreamChunk } from '@/types/chat';

function buildContext(): { context: SSEHandlerContext; dispatch: ReturnType<typeof vi.fn> } {
  const dispatch = vi.fn();
  const setProgressMessageId = vi.fn();
  const withContext = (extra: Record<string, unknown>) => extra;
  const t = (key: string, _opts?: unknown) => key;
  const context = {
    dispatch,
    withContext,
    t,
    progressMessageId: null,
    setProgressMessageId,
    assistantMessageId: 'assistant-1',
    executionStepsRef: { current: [] },
    emittedStepKeysRef: { current: new Set<string>() },
    reasoningBufRef: { current: '' },
    traceStepsRef: { current: [] },
    traceReasoningRef: { current: '' },
  } as unknown as SSEHandlerContext;
  return { context, dispatch };
}

describe('handleExecutionStep — compaction interception (Task 3.2)', () => {
  it('dispatches STREAM_COMPACTION_START on phase=start chunk', () => {
    const { context, dispatch } = buildContext();
    const chunk: ChatStreamChunk = {
      type: 'execution_step',
      content: '',
      metadata: {
        step_type: 'compaction',
        step_label: 'compaction_start',
        phase: 'start',
        estimated_duration_seconds: 30,
      },
    };

    handleExecutionStep(chunk, context);

    expect(dispatch).toHaveBeenCalledTimes(1);
    expect(dispatch).toHaveBeenCalledWith({
      type: 'STREAM_COMPACTION_START',
      payload: { estimatedDurationSeconds: 30, strategy: undefined },
    });
    // The generic accumulator must not have queued a step message.
    expect(context.executionStepsRef.current).toEqual([]);
  });

  it('dispatches STREAM_COMPACTION_DONE with tokens / duration / strategy', () => {
    const { context, dispatch } = buildContext();
    const chunk: ChatStreamChunk = {
      type: 'execution_step',
      content: '',
      metadata: {
        step_type: 'compaction',
        step_label: 'compaction_done',
        phase: 'done',
        tokens_saved: 4800,
        duration_ms: 7200,
        strategy: 'multi_chunk',
      },
    };

    handleExecutionStep(chunk, context);

    expect(dispatch).toHaveBeenCalledWith({
      type: 'STREAM_COMPACTION_DONE',
      payload: {
        tokensSaved: 4800,
        durationMs: 7200,
        strategy: 'multi_chunk',
      },
    });
    expect(context.executionStepsRef.current).toEqual([]);
  });

  it('propagates strategy="truncation" for fallback path', () => {
    const { context, dispatch } = buildContext();
    const chunk: ChatStreamChunk = {
      type: 'execution_step',
      content: '',
      metadata: {
        step_type: 'compaction',
        step_label: 'compaction_done',
        strategy: 'truncation',
      },
    };

    handleExecutionStep(chunk, context);

    expect(dispatch).toHaveBeenCalledWith({
      type: 'STREAM_COMPACTION_DONE',
      payload: {
        tokensSaved: undefined,
        durationMs: undefined,
        strategy: 'truncation',
      },
    });
  });

  it('defaults tokensSaved to undefined when compaction_done omits tokens_saved', () => {
    const { context, dispatch } = buildContext();
    const chunk: ChatStreamChunk = {
      type: 'execution_step',
      content: '',
      metadata: {
        step_type: 'compaction',
        step_label: 'compaction_done',
        strategy: 'single_chunk',
      },
    };

    handleExecutionStep(chunk, context);

    expect(dispatch).toHaveBeenCalledWith({
      type: 'STREAM_COMPACTION_DONE',
      payload: { tokensSaved: undefined, durationMs: undefined, strategy: 'single_chunk' },
    });
  });

  it('does NOT intercept non-compaction execution_step chunks (regression guard)', () => {
    const { context, dispatch } = buildContext();
    // A regular execution_step chunk (eg from a tool) must not trigger any
    // compaction dispatch; the generic accumulator should run as before.
    const chunk: ChatStreamChunk = {
      type: 'execution_step',
      content: '',
      metadata: {
        step_type: 'tool',
        step_name: 'search_emails',
        i18n_key: 'progress.tool_running',
      },
    };

    handleExecutionStep(chunk, context);

    // Neither of our new actions should appear.
    for (const call of dispatch.mock.calls) {
      expect(call[0].type).not.toBe('STREAM_COMPACTION_START');
      expect(call[0].type).not.toBe('STREAM_COMPACTION_DONE');
    }
  });

  it('falls through to the generic handler when step_label is unknown', () => {
    const { context, dispatch } = buildContext();
    const chunk: ChatStreamChunk = {
      type: 'execution_step',
      content: '',
      metadata: {
        step_type: 'compaction',
        step_label: 'compaction_weird_future_phase',
      },
    };

    handleExecutionStep(chunk, context);

    // No compaction action emitted, but the generic accumulator runs so the
    // user still gets feedback (resilience over silence).
    for (const call of dispatch.mock.calls) {
      expect(call[0].type).not.toBe('STREAM_COMPACTION_START');
      expect(call[0].type).not.toBe('STREAM_COMPACTION_DONE');
    }
  });
});
