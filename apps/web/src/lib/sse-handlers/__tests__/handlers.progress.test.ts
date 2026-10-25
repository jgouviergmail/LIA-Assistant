/**
 * sse-handlers — progress feedback pipeline.
 *
 * Covers getProgressMessage (all event types and fallbacks),
 * handleRouterDecision and the generic handleExecutionStep accumulator
 * (step dedup, live-reasoning buffer with HTML escaping, MAX_VISIBLE_STEPS
 * cap). Compaction interception is covered by compaction-handler.test.ts.
 */

import { describe, it, expect, vi, afterEach } from 'vitest';

import {
  getProgressMessage,
  handleRouterDecision,
  handleExecutionStep,
  handleToken,
} from '@/lib/sse-handlers/handlers';
import type { ChatStreamChunk } from '@/types/chat';
import type { SSEHandlerContext } from '@/lib/sse-handlers/types';
import { buildHandlerContext, dispatchedOfType } from './context-fixture';

afterEach(() => {
  vi.restoreAllMocks();
});

function executionStepChunk(metadata: Record<string, unknown> | undefined): ChatStreamChunk {
  return { type: 'execution_step', content: '', metadata } as ChatStreamChunk;
}

describe('getProgressMessage', () => {
  const tKey = ((key: string) => key) as SSEHandlerContext['t'];

  it('router_decision picks a random phrase from the analyzing pool', () => {
    const pool = ['phrase-a', 'phrase-b', 'phrase-c'];
    const t = ((key: string, opts?: { returnObjects?: boolean }) =>
      key === 'hitl.progress.analyzingMessages' && opts?.returnObjects
        ? pool
        : key) as SSEHandlerContext['t'];

    vi.spyOn(Math, 'random').mockReturnValue(0.99);
    expect(getProgressMessage('router_decision', t)).toBe('phrase-c');

    vi.spyOn(Math, 'random').mockReturnValue(0);
    expect(getProgressMessage('router_decision', t)).toBe('phrase-a');
  });

  it('router_decision falls back to the static analyzing label without a pool', () => {
    // Key-echo t returns a string (not an array) for the pool lookup.
    expect(getProgressMessage('router_decision', tKey)).toBe('hitl.progress.analyzing');
  });

  it('hitl_interrupt_metadata renders the access-validation label', () => {
    expect(getProgressMessage('hitl_interrupt_metadata', tKey)).toBe('hitl.validating_access');
  });

  it('execution_step renders emoji + translated step when the i18n key resolves', () => {
    const message = getProgressMessage('execution_step', tKey, {
      emoji: '📅',
      i18n_key: 'calendar_search',
    });

    expect(message).toBe('*📅 execution.steps.calendar_search*');
  });

  it('execution_step whose label no language knows reads as thinking', () => {
    const tEmptySteps = ((key: string, opts?: { defaultValue?: string }) =>
      key.startsWith('execution.steps.')
        ? (opts?.defaultValue ?? '')
        : key) as SSEHandlerContext['t'];

    const message = getProgressMessage('execution_step', tEmptySteps, {
      emoji: '🔎',
      i18n_key: 'unknown_step',
    });

    expect(message).toBe('hitl.progress.thinking');
  });

  it('execution_step without metadata and unknown types fall back to thinking', () => {
    expect(getProgressMessage('execution_step', tKey)).toBe('hitl.progress.thinking');
    expect(getProgressMessage('someday_new_event', tKey)).toBe('hitl.progress.thinking');
  });
});

describe('handleRouterDecision', () => {
  const routerChunk: ChatStreamChunk = {
    type: 'router_decision',
    content: '',
    metadata: {
      intention: 'actionable',
      confidence: 0.92,
      context_label: 'calendar',
      next_node: 'planner',
      reasoning: null,
    },
  } as ChatStreamChunk;

  it('dispatches ROUTER_DECISION + SSE_CONNECTED and creates the progress message', () => {
    const { context, dispatch, state } = buildHandlerContext();

    handleRouterDecision(routerChunk, context);

    expect(dispatchedOfType(dispatch, 'ROUTER_DECISION')).toEqual([routerChunk.metadata]);
    expect(dispatchedOfType(dispatch, 'SSE_CONNECTED')).toHaveLength(1);
    const starts = dispatchedOfType(dispatch, 'STREAM_START') as Array<{
      messageId: string;
      initialContent: string;
    }>;
    expect(starts).toHaveLength(1);
    expect(starts[0].messageId).toBe('assistant-1');
    expect(starts[0].initialContent).toBe('hitl.progress.analyzing');
    expect(state.progressMessageId).toBe('assistant-1');
  });

  it('resets accumulated steps/keys and registers the router step for dedup', () => {
    const { context } = buildHandlerContext();
    context.executionStepsRef.current = ['*stale step*'];
    context.emittedStepKeysRef.current = new Set(['stale_key']);

    handleRouterDecision(routerChunk, context);

    expect(context.executionStepsRef.current).toEqual(['hitl.progress.analyzing']);
    expect(context.emittedStepKeysRef.current).toEqual(new Set(['router_decision']));
  });

  it('replaces the existing progress message instead of creating a second one', () => {
    const { context, dispatch } = buildHandlerContext({ progressMessageId: 'assistant-1' });

    handleRouterDecision(routerChunk, context);

    expect(dispatchedOfType(dispatch, 'STREAM_START')).toHaveLength(0);
    expect(dispatchedOfType(dispatch, 'STREAM_REPLACE')).toHaveLength(1);
  });
});

describe('handleExecutionStep — generic accumulator', () => {
  it('accumulates steps and replaces the progress content', () => {
    const { context, dispatch } = buildHandlerContext({ progressMessageId: 'assistant-1' });

    handleExecutionStep(executionStepChunk({ emoji: '📅', i18n_key: 'calendar_search' }), context);

    expect(context.executionStepsRef.current).toEqual(['*📅 execution.steps.calendar_search*']);
    expect(dispatchedOfType(dispatch, 'STREAM_REPLACE')).toEqual([
      { content: '*📅 execution.steps.calendar_search*', phase: 'progress' },
    ]);
  });

  it('creates the progress message when the step arrives before router_decision', () => {
    const { context, dispatch, state } = buildHandlerContext();

    handleExecutionStep(executionStepChunk({ emoji: '🧠', i18n_key: 'thinking' }), context);

    expect(dispatchedOfType(dispatch, 'STREAM_START')).toHaveLength(1);
    expect(state.progressMessageId).toBe('assistant-1');
  });

  it('deduplicates steps already emitted under the same i18n key', () => {
    const { context, dispatch } = buildHandlerContext({ progressMessageId: 'assistant-1' });
    context.emittedStepKeysRef.current = new Set(['planner_generation']);

    handleExecutionStep(
      executionStepChunk({ emoji: '📋', i18n_key: 'planner_generation' }),
      context
    );

    expect(dispatch).not.toHaveBeenCalled();
    expect(context.executionStepsRef.current).toEqual([]);
  });

  it('updates the ONE line of a tool in place with what its calls did', () => {
    // 2026-10-24: a call starts, then finishes with the read's counts; the
    // same tool called again counts ×2 — one line, never two, never stale.
    const { context } = buildHandlerContext({ progressMessageId: 'assistant-1' });
    const step = (stepKey: string, outcome?: Record<string, number>) =>
      handleExecutionStep(
        executionStepChunk({
          emoji: '🔍',
          i18n_key: 'search_emails',
          step_key: stepKey,
          ...(outcome ? { outcome } : {}),
        }),
        context
      );

    step('call_0');
    expect(context.executionStepsRef.current).toEqual(['*🔍 execution.steps.search_emails*']);
    step('call_0', { failed: 0, found: 12, shown: 5 });
    step('call_1');
    step('call_1', { failed: 1 });

    expect(context.executionStepsRef.current).toHaveLength(1);
    const [line] = context.executionStepsRef.current;
    for (const word of ['calls', 'found', 'shown', 'failed'])
      expect(line).toContain(`execution.outcome.${word}`);
    expect(context.traceStepsRef.current).toEqual([
      expect.objectContaining({ outcome: { calls: 2, found: 12, shown: 5, failed: 1 } }),
    ]);
  });

  it('counts on the line of a label the trace cannot name, and draws no trace step', () => {
    // No translation for the key: the line falls back, the trace has no step for it.
    const t = (key: string) => (key.startsWith('execution.steps.unnamed') ? '' : key);
    const { context } = buildHandlerContext({ progressMessageId: 'assistant-1', t });
    const step = (outcome?: Record<string, number>) =>
      handleExecutionStep(
        executionStepChunk({
          emoji: '🔍',
          i18n_key: 'unnamed',
          step_key: 'call_0',
          ...(outcome ? { outcome } : {}),
        }),
        context
      );

    step();
    step({ failed: 0, found: 3 });

    expect(context.executionStepsRef.current).toHaveLength(1);
    expect(context.traceStepsRef.current).toEqual([]);
  });

  it('never rewrites a line drawn after the answer replaced the steps', () => {
    // The first answer token replaces the lines and keeps the tallies, so
    // the trace still learns: a late step of an earlier label must not
    // rewrite whatever now sits at its old index.
    const { context } = buildHandlerContext({ progressMessageId: 'assistant-1' });
    const toolStep = (key: string, outcome?: Record<string, number>) =>
      handleExecutionStep(
        executionStepChunk({
          emoji: '🔍',
          i18n_key: key,
          step_key: `${key}-call`,
          ...(outcome ? { outcome } : {}),
        }),
        context
      );

    toolStep('search_emails');
    handleToken({ type: 'token', content: 'Hello' } as ChatStreamChunk, context);
    toolStep('search_contacts');
    toolStep('search_emails', { failed: 0, found: 4 });

    expect(context.executionStepsRef.current).toEqual(['*🔍 execution.steps.search_contacts*']);
    expect(context.traceStepsRef.current[0]).toEqual(
      expect.objectContaining({ outcome: { found: 4 } })
    );
  });

  it('shows the total of a pipeline tool on its first and only line', () => {
    const { context } = buildHandlerContext({ progressMessageId: 'assistant-1' });

    handleExecutionStep(
      executionStepChunk({
        emoji: '📧',
        i18n_key: 'send_email',
        outcome: { calls: 3, found: 0, failed: 0 },
      }),
      context
    );

    expect(context.executionStepsRef.current).toEqual([
      '*📧 execution.steps.send_emailexecution.outcome.leadexecution.outcome.calls*',
    ]);
  });

  it('collapses older steps beyond the visible cap with a hidden-count line', () => {
    const { context, dispatch } = buildHandlerContext({ progressMessageId: 'assistant-1' });
    context.executionStepsRef.current = Array.from({ length: 11 }, (_, i) => `*step ${i}*`);

    handleExecutionStep(executionStepChunk({ emoji: '⚙️', i18n_key: 'final_step' }), context);

    const replaces = dispatchedOfType(dispatch, 'STREAM_REPLACE') as Array<{ content: string }>;
    const lines = replaces[0].content.split('\n');
    // 12 steps accumulated, 10 visible + 1 "previous steps" indicator.
    expect(lines).toHaveLength(11);
    expect(lines[0]).toContain('2 execution.steps.previous_steps');
    expect(lines[10]).toBe('*⚙️ execution.steps.final_step*');
  });
});

describe('handleExecutionStep — live reasoning (💭)', () => {
  it('accumulates reasoning deltas into the dedicated buffer, not the steps', () => {
    const { context } = buildHandlerContext({ progressMessageId: 'assistant-1' });

    handleExecutionStep(
      executionStepChunk({ step_type: 'reasoning', delta: 'First thought. ' }),
      context
    );
    handleExecutionStep(
      executionStepChunk({ step_type: 'reasoning', delta: 'Second thought.' }),
      context
    );

    expect(context.reasoningBufRef.current).toBe('First thought. Second thought.');
    expect(context.executionStepsRef.current).toEqual([]);
  });

  it('renders the reasoning block under the steps with a title header', () => {
    const { context, dispatch } = buildHandlerContext({ progressMessageId: 'assistant-1' });
    context.executionStepsRef.current = ['*step*'];

    handleExecutionStep(
      executionStepChunk({ step_type: 'reasoning', delta: 'Considering options.' }),
      context
    );

    const replaces = dispatchedOfType(dispatch, 'STREAM_REPLACE') as Array<{ content: string }>;
    const content = replaces[0].content;
    expect(content).toContain('*step*');
    expect(content).toContain('<div class="lia-reasoning">');
    expect(content).toContain('💭 execution.reasoning.title');
    expect(content).toContain('<p>Considering options.</p>');
  });

  it('HTML-escapes reasoning text so the model cannot inject markup', () => {
    const { context, dispatch } = buildHandlerContext({ progressMessageId: 'assistant-1' });

    handleExecutionStep(
      executionStepChunk({
        step_type: 'reasoning',
        delta: 'Use <script>alert("x")</script> & "quotes"',
      }),
      context
    );

    const replaces = dispatchedOfType(dispatch, 'STREAM_REPLACE') as Array<{ content: string }>;
    expect(replaces[0].content).toContain(
      '&lt;script&gt;alert(&quot;x&quot;)&lt;/script&gt; &amp; &quot;quotes&quot;'
    );
    expect(replaces[0].content).not.toContain('<script>');
  });

  it('splits reasoning on blank lines into paragraphs and flattens inner newlines', () => {
    const { context, dispatch } = buildHandlerContext({ progressMessageId: 'assistant-1' });

    handleExecutionStep(
      executionStepChunk({
        step_type: 'reasoning',
        delta: 'First paragraph\nsame sentence.\n\nSecond paragraph.',
      }),
      context
    );

    const replaces = dispatchedOfType(dispatch, 'STREAM_REPLACE') as Array<{ content: string }>;
    expect(replaces[0].content).toContain('<p>First paragraph same sentence.</p>');
    expect(replaces[0].content).toContain('<p>Second paragraph.</p>');
  });

  it('re-renders without appending when a reasoning event has no delta', () => {
    const { context, dispatch } = buildHandlerContext({ progressMessageId: 'assistant-1' });
    context.reasoningBufRef.current = 'existing';

    handleExecutionStep(executionStepChunk({ step_type: 'reasoning' }), context);

    expect(context.reasoningBufRef.current).toBe('existing');
    expect(dispatchedOfType(dispatch, 'STREAM_REPLACE')).toHaveLength(1);
  });

  it('renders steps alone when the reasoning buffer is blank', () => {
    const { context, dispatch } = buildHandlerContext({ progressMessageId: 'assistant-1' });
    context.reasoningBufRef.current = '   ';

    handleExecutionStep(executionStepChunk({ emoji: '🧠', i18n_key: 'k1' }), context);

    const replaces = dispatchedOfType(dispatch, 'STREAM_REPLACE') as Array<{ content: string }>;
    expect(replaces[0].content).toBe('*🧠 execution.steps.k1*');
    expect(replaces[0].content).not.toContain('lia-reasoning');
  });
});
