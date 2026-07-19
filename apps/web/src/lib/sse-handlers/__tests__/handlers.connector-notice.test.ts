/**
 * SSE handlers — connector error notice interception (Lot 3 P3, ADR-134).
 *
 * `execution_step` chunks with `step_type: "tool_error"` are intercepted
 * BEFORE the generic progress accumulator (same pattern as compaction):
 * they dispatch CONNECTOR_NOTICE_ADD and never pollute the live steps nor
 * the Lot 2 execution trace. Malformed payloads are dropped silently.
 */

import { describe, it, expect } from 'vitest';

import { handleExecutionStep } from '@/lib/sse-handlers/handlers';
import { buildHandlerContext } from './context-fixture';
import type { ChatStreamChunk } from '@/types/chat';
import type { ChatAction } from '@/types/chat-state';

function toolErrorChunk(metadata: Record<string, unknown>): ChatStreamChunk {
  return {
    type: 'execution_step',
    content: '',
    metadata: { step_type: 'tool_error', ...metadata },
  } as ChatStreamChunk;
}

function noticeActions(dispatch: { mock: { calls: unknown[][] } }): ChatAction[] {
  return dispatch.mock.calls
    .map(c => c[0] as ChatAction)
    .filter(a => a.type === 'CONNECTOR_NOTICE_ADD');
}

describe('handleExecutionStep — tool_error interception', () => {
  it('dispatches CONNECTOR_NOTICE_ADD for a valid reconnect payload', () => {
    const { context, dispatch } = buildHandlerContext();

    handleExecutionStep(
      toolErrorChunk({
        connector_type: 'google_gmail',
        action: 'reconnect',
        tool_name: 'search_emails_tool',
      }),
      context
    );

    const actions = noticeActions(dispatch);
    expect(actions).toHaveLength(1);
    if (actions[0].type !== 'CONNECTOR_NOTICE_ADD') throw new Error('unreachable');
    expect(actions[0].payload.notice).toEqual({
      connectorType: 'google_gmail',
      action: 'reconnect',
      toolName: 'search_emails_tool',
    });
  });

  it('does not pollute the live steps nor the execution trace', () => {
    const { context } = buildHandlerContext();

    handleExecutionStep(
      toolErrorChunk({ connector_type: 'google_gmail', action: 'rate_limit', tool_name: 't' }),
      context
    );

    expect(context.executionStepsRef.current).toHaveLength(0);
    expect(context.traceStepsRef.current).toHaveLength(0);
  });

  it('drops a payload with an unknown action', () => {
    const { context, dispatch } = buildHandlerContext();

    handleExecutionStep(
      toolErrorChunk({ connector_type: 'google_gmail', action: 'explode', tool_name: 't' }),
      context
    );

    expect(noticeActions(dispatch)).toHaveLength(0);
  });

  it('drops a payload without connector_type', () => {
    const { context, dispatch } = buildHandlerContext();

    handleExecutionStep(toolErrorChunk({ action: 'reconnect', tool_name: 't' }), context);

    expect(noticeActions(dispatch)).toHaveLength(0);
  });
});

describe('handleExecutionStep — tool_error default tool name', () => {
  it('defaults toolName to "unknown" when the payload omits tool_name', () => {
    const { context, dispatch } = buildHandlerContext();
    handleExecutionStep(
      toolErrorChunk({ connector_type: 'google_gmail', action: 'reconnect' }),
      context
    );
    const add = dispatch.mock.calls
      .map(c => c[0] as ChatAction)
      .find(a => a.type === 'CONNECTOR_NOTICE_ADD');
    expect(add).toBeDefined();
    if (add?.type !== 'CONNECTOR_NOTICE_ADD') throw new Error('unreachable');
    expect(add.payload.notice.toolName).toBe('unknown');
  });
});
