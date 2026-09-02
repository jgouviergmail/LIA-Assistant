/**
 * Hydration of the persisted ⚙ execution trace (ADR-133 V2).
 *
 * The backend archives `{steps: [{emoji, i18n_key, category}], duration_ms}`
 * under `message_metadata.execution_trace` — i18n keys only (PII guard).
 * `executionTraceFromMetadata` re-resolves the labels client-side so hydrated
 * traces render through the exact same `ExecutionTraceDisclosure` path as live
 * ones. Malformed or unresolvable payloads must degrade to `undefined`
 * (no disclosure), never throw: this runs on every history row.
 */
import { describe, expect, it } from 'vitest';

import { executionTraceFromMetadata } from '../execution-trace-hydration';
import { MAX_TRACE_STEPS } from '@/types/execution-trace';

const KNOWN_KEYS: Record<string, string> = {
  'execution.steps.router_decision': 'Analyzing request',
  'execution.steps.planner_generation': 'Planning',
  'execution.steps.get_contacts': 'Fetching contacts',
};

const t = (key: string, options?: { defaultValue?: string }): string =>
  KNOWN_KEYS[key] ?? options?.defaultValue ?? '';

function tracePayload(steps: unknown[], durationMs?: unknown): Record<string, unknown> {
  return { execution_trace: { steps, duration_ms: durationMs } };
}

describe('executionTraceFromMetadata', () => {
  it('returns undefined without metadata or without a trace key', () => {
    expect(executionTraceFromMetadata(undefined, t)).toBeUndefined();
    expect(executionTraceFromMetadata(null, t)).toBeUndefined();
    expect(executionTraceFromMetadata({}, t)).toBeUndefined();
    expect(executionTraceFromMetadata({ run_id: 'r1' }, t)).toBeUndefined();
  });

  it('hydrates steps with resolved labels, duration and empty reasoning', () => {
    const metadata = tracePayload(
      [
        { emoji: '🧭', i18n_key: 'router_decision', category: 'system' },
        { emoji: '🔍', i18n_key: 'get_contacts', category: 'tool' },
      ],
      2300
    );

    expect(executionTraceFromMetadata(metadata, t)).toEqual({
      steps: [
        { emoji: '🧭', label: 'Analyzing request', category: 'system' },
        { emoji: '🔍', label: 'Fetching contacts', category: 'tool' },
      ],
      reasoning: '',
      durationMs: 2300,
    });
  });

  it('drops steps whose i18n key does not resolve', () => {
    const metadata = tracePayload([
      { emoji: '🧭', i18n_key: 'router_decision', category: 'system' },
      { emoji: '❓', i18n_key: 'unknown_step_key', category: 'system' },
    ]);

    expect(executionTraceFromMetadata(metadata, t)?.steps).toEqual([
      { emoji: '🧭', label: 'Analyzing request', category: 'system' },
    ]);
  });

  it('returns undefined when no step resolves', () => {
    const metadata = tracePayload([{ emoji: '❓', i18n_key: 'nope', category: 'system' }]);

    expect(executionTraceFromMetadata(metadata, t)).toBeUndefined();
  });

  it('defaults emoji and whitelists category', () => {
    const metadata = tracePayload([
      { i18n_key: 'planner_generation', category: 'martian' },
      { emoji: '', i18n_key: 'router_decision' },
    ]);

    expect(executionTraceFromMetadata(metadata, t)?.steps).toEqual([
      { emoji: '⚙️', label: 'Planning', category: 'system' },
      { emoji: '⚙️', label: 'Analyzing request', category: 'system' },
    ]);
  });

  it('skips malformed step entries without throwing', () => {
    const metadata = tracePayload([
      null,
      'not-a-step',
      { emoji: '🧭' },
      { emoji: '🧭', i18n_key: 'router_decision', category: 'system' },
    ]);

    expect(executionTraceFromMetadata(metadata, t)?.steps).toHaveLength(1);
  });

  it('returns undefined on malformed trace payloads', () => {
    expect(executionTraceFromMetadata({ execution_trace: 'oops' }, t)).toBeUndefined();
    expect(executionTraceFromMetadata({ execution_trace: { steps: 'oops' } }, t)).toBeUndefined();
    expect(executionTraceFromMetadata({ execution_trace: null }, t)).toBeUndefined();
  });

  it('omits durationMs when absent or not a number', () => {
    const steps = [{ emoji: '🧭', i18n_key: 'router_decision', category: 'system' }];

    expect(executionTraceFromMetadata(tracePayload(steps), t)?.durationMs).toBeUndefined();
    expect(executionTraceFromMetadata(tracePayload(steps, 'slow'), t)?.durationMs).toBeUndefined();
  });

  it('caps hydrated steps to MAX_TRACE_STEPS keeping head and tail, with the omission counted', () => {
    const steps = Array.from({ length: MAX_TRACE_STEPS + 5 }, () => ({
      emoji: '🔍',
      i18n_key: 'get_contacts',
      category: 'tool',
    }));
    steps[0] = { emoji: '🧭', i18n_key: 'router_decision', category: 'system' };
    steps[steps.length - 1] = { emoji: '🧭', i18n_key: 'router_decision', category: 'system' };

    const hydrated = executionTraceFromMetadata(tracePayload(steps), t);

    expect(hydrated?.steps).toHaveLength(MAX_TRACE_STEPS);
    // Head survives: the very first persisted step is still rendered.
    expect(hydrated?.steps[0]?.label).toBe('Analyzing request');
    // Tail survives too, and the gap is stated exactly.
    expect(hydrated?.steps.at(-1)?.label).toBe('Analyzing request');
    expect(hydrated?.omittedSteps).toBe(5);
  });

  it('sets no omission count when hydrated steps fit the cap', () => {
    const steps = [{ emoji: '🧭', i18n_key: 'router_decision', category: 'system' }];
    expect(executionTraceFromMetadata(tracePayload(steps), t)?.omittedSteps).toBeUndefined();
  });
});
