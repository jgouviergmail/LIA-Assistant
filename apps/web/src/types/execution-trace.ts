/**
 * Execution-trace types (Lot 2 P2-V1 — "backstage per message").
 *
 * The per-turn record of the agentic work — execution steps + live reasoning
 * + duration — captured at the progress→answer flip (where the live steps are
 * otherwise wiped) and attached to the assistant message so it survives the
 * response instead of vanishing. Rendered as a collapsed disclosure under the
 * bubble; V1 is session-only (not persisted to message_metadata).
 */

/** Coarse grouping mirroring the backend DisplayMetadata.category vocabulary. */
export type TraceStepCategory = 'system' | 'agent' | 'tool' | 'context';

/** One captured execution step, ready to render (already translated label). */
export interface ExecutionTraceStep {
  /** Display emoji from the step metadata (defaulted when absent). */
  emoji: string;
  /** Human-readable, already-translated label. */
  label: string;
  /** Grouping bucket for the disclosure. */
  category: TraceStepCategory;
}

/** The full backstage record attached to a completed assistant message. */
export interface ExecutionTrace {
  steps: ExecutionTraceStep[];
  /** Live reasoning (💭) accumulated during the turn; '' when none. */
  reasoning: string;
  /** Wall-clock duration from the done metadata, when available. */
  durationMs?: number;
}

/**
 * Hard cap on retained steps per trace: a FOR_EACH over hundreds of items
 * must never balloon the DOM/state. Older steps beyond the cap are dropped
 * (the tail is the most informative for "what did it just do").
 */
export const MAX_TRACE_STEPS = 100;
