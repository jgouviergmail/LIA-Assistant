/**
 * SSE handlers — execution-trace capture (Lot 2 P2-V1).
 *
 * Proves the core inversion of the ephemeral behavior: steps accumulated in
 * the trace refs SURVIVE the progress→answer flip (which wipes the live refs)
 * and are attached to the message at `done`. Also proves the no-trace skip
 * for a pure conversation reply.
 */

import { describe, it, expect } from 'vitest';

import {
  handleRouterDecision,
  handleExecutionStep,
  handleToken,
  handleDone,
} from '@/lib/sse-handlers/handlers';
import { buildHandlerContext } from './context-fixture';
import type { ChatStreamChunk } from '@/types/chat';
import type { ChatAction } from '@/types/chat-state';

type TraceAttachAction = Extract<ChatAction, { type: 'TRACE_ATTACH' }>;

// execution.steps.* → key tail; every other key echoes; honors defaultValue.
const traceT = (key: string, opts?: Record<string, unknown>) => {
  if (key.startsWith('execution.steps.')) return key.slice('execution.steps.'.length);
  return (opts?.defaultValue as string) ?? key;
};

function routerChunk(): ChatStreamChunk {
  return {
    type: 'router_decision',
    content: '',
    metadata: { intention: 'actionable', confidence: 0.9, next_node: 'planner' },
  } as ChatStreamChunk;
}

function stepChunk(i18nKey: string, category = 'system'): ChatStreamChunk {
  return {
    type: 'execution_step',
    content: '',
    metadata: { emoji: '📋', i18n_key: i18nKey, category },
  } as ChatStreamChunk;
}

function reasoningChunk(delta: string): ChatStreamChunk {
  return {
    type: 'execution_step',
    content: '',
    metadata: { step_type: 'reasoning', delta },
  } as ChatStreamChunk;
}

function traceAttach(dispatch: { mock: { calls: unknown[][] } }): TraceAttachAction | undefined {
  const call = dispatch.mock.calls.find(c => (c[0] as ChatAction).type === 'TRACE_ATTACH');
  return call?.[0] as TraceAttachAction | undefined;
}

describe('handlers — execution trace capture', () => {
  it('captures steps that survive the answer flip and attaches them at done', () => {
    const { context, dispatch } = buildHandlerContext({ t: traceT });

    handleRouterDecision(routerChunk(), context);
    handleExecutionStep(stepChunk('planner_generation'), context);
    handleExecutionStep(reasoningChunk('Thinking hard. '), context);
    handleExecutionStep(stepChunk('send_email', 'tool'), context);

    // Answer flip: wipes the LIVE refs, must NOT wipe the trace refs.
    handleToken({ type: 'token', content: 'Hello' } as ChatStreamChunk, context);
    expect(context.executionStepsRef.current).toHaveLength(0);
    expect(context.traceStepsRef.current.length).toBeGreaterThan(0);

    handleDone(
      { type: 'done', content: '', metadata: { duration_ms: 4200 } } as ChatStreamChunk,
      context
    );

    const attach = traceAttach(dispatch);
    expect(attach).toBeDefined();
    const { trace, messageId } = attach!.payload;
    expect(messageId).toBe('assistant-1');
    expect(trace.durationMs).toBe(4200);
    expect(trace.reasoning).toContain('Thinking hard.');
    // router + planner + send_email (reasoning is separate, not a step)
    expect(trace.steps.map(s => s.label)).toEqual([
      'router_decision',
      'planner_generation',
      'send_email',
    ]);
    expect(trace.steps.find(s => s.label === 'send_email')?.category).toBe('tool');
  });

  it('attaches nothing when no step was captured (pure conversation)', () => {
    const { context, dispatch } = buildHandlerContext();

    handleToken({ type: 'token', content: 'Hi there' } as ChatStreamChunk, context);
    handleDone({ type: 'done', content: '', metadata: {} } as ChatStreamChunk, context);

    expect(traceAttach(dispatch)).toBeUndefined();
  });
});
