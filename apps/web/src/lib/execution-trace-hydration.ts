/**
 * Hydrate the persisted ⚙ execution trace from message metadata (ADR-133 V2).
 *
 * The backend archives `{steps: [{emoji, i18n_key, category}], duration_ms}`
 * under `message_metadata.execution_trace` — i18n keys only, never free text
 * (PII guard), and never the reasoning stream. Labels are re-resolved here with
 * the same `execution.steps.<key>` translations the live bubble uses, so a
 * hydrated trace flows through the exact same `ExecutionTrace` type and
 * `ExecutionTraceDisclosure` render path as a live one (labels frozen at
 * hydration time, matching live traces frozen at capture time).
 *
 * Runs on every history row: malformed payloads degrade to `undefined`
 * (no disclosure) instead of throwing.
 */

import type {
  ExecutionTrace,
  ExecutionTraceStep,
  TraceStepCategory,
} from '@/types/execution-trace';
import { MAX_TRACE_STEPS } from '@/types/execution-trace';

/** Metadata key written by the backend (`FIELD_EXECUTION_TRACE`). */
const EXECUTION_TRACE_METADATA_KEY = 'execution_trace';

const TRACE_CATEGORIES: ReadonlySet<string> = new Set(['system', 'agent', 'tool', 'context']);

/** Minimal translator contract — satisfied by i18next's `t`. */
type TranslateFn = (key: string, options?: { defaultValue?: string }) => string;

function hydrateStep(raw: unknown, t: TranslateFn): ExecutionTraceStep | null {
  if (typeof raw !== 'object' || raw === null) return null;
  const step = raw as Record<string, unknown>;
  const i18nKey = step.i18n_key;
  if (typeof i18nKey !== 'string' || !i18nKey) return null;
  const label = t(`execution.steps.${i18nKey}`, { defaultValue: '' });
  if (!label) return null;
  const category = step.category;
  return {
    emoji: typeof step.emoji === 'string' && step.emoji ? step.emoji : '⚙️',
    label,
    category:
      typeof category === 'string' && TRACE_CATEGORIES.has(category)
        ? (category as TraceStepCategory)
        : 'system',
  };
}

/**
 * Build an `ExecutionTrace` from persisted message metadata, if any.
 *
 * @param metadata - The message's `message_metadata` payload.
 * @param t - Translator resolving `execution.steps.<i18n_key>` labels.
 * @returns The hydrated trace, or `undefined` when the metadata carries no
 *   renderable trace (absent, malformed, or no resolvable step).
 */
export function executionTraceFromMetadata(
  metadata: Record<string, unknown> | null | undefined,
  t: TranslateFn
): ExecutionTrace | undefined {
  const raw = metadata?.[EXECUTION_TRACE_METADATA_KEY];
  if (typeof raw !== 'object' || raw === null) return undefined;
  const trace = raw as Record<string, unknown>;
  if (!Array.isArray(trace.steps)) return undefined;

  const steps = trace.steps
    .map(step => hydrateStep(step, t))
    .filter((step): step is ExecutionTraceStep => step !== null)
    .slice(-MAX_TRACE_STEPS);
  if (steps.length === 0) return undefined;

  const durationMs = trace.duration_ms;
  return {
    steps,
    // The reasoning stream is never persisted (PII guard) — hydrated traces
    // render without the 💭 block, by design.
    reasoning: '',
    ...(typeof durationMs === 'number' ? { durationMs } : {}),
  };
}
