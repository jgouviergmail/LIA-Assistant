/**
 * Execution-trace types (Lot 2 P2-V1 — "backstage per message").
 *
 * The per-turn record of the agentic work — execution steps + live reasoning
 * + duration — captured at the progress→answer flip (where the live steps are
 * otherwise wiped) and attached to the assistant message so it survives the
 * response instead of vanishing. Rendered as a collapsed disclosure under the
 * bubble. Since ADR-133 V2 the trace is also persisted to `message_metadata`
 * (i18n keys only, no reasoning) and hydrated on history load via
 * `lib/execution-trace-hydration.ts` — a reloaded trace has no 💭 block.
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
  /**
   * Steps dropped by the retention cap, when any (Lot C, 2026-09). Carried so
   * the disclosure can state the TRUE total — a shown count is a claim: exact
   * or absent. Absent when every step fit `MAX_TRACE_STEPS`.
   */
  omittedSteps?: number;
}

/**
 * Hard cap on retained steps per trace: a FOR_EACH over hundreds of items
 * must never balloon the DOM/state.
 */
export const MAX_TRACE_STEPS = 100;

/**
 * Opening steps preserved when the cap bites (Lot C, 2026-09). Tail-only
 * retention silently erased the turn's FIRST actions — precisely the ones an
 * injected instruction would have triggered early in a long loop. The tail
 * keeps the larger share ("what did it just do" stays primary); the head
 * keeps the turn's opening acts visible.
 */
export const TRACE_HEAD_KEEP = 20;

/**
 * Apply the retention cap, keeping head + tail and counting the omission.
 *
 * Single implementation shared by the live path (chat reducer `TRACE_ATTACH`)
 * and the reload path (`execution-trace-hydration`), so a reloaded trace can
 * never disagree with the live one on WHICH steps survived.
 *
 * @param steps - Steps in emission order.
 * @returns The retained steps plus the exact number omitted (0 when none).
 */
export function capTraceSteps(steps: ExecutionTraceStep[]): {
  steps: ExecutionTraceStep[];
  omitted: number;
} {
  if (steps.length <= MAX_TRACE_STEPS) {
    return { steps, omitted: 0 };
  }
  // Clamp so a future constant change can never make `slice(-0)` return the
  // whole array (tail must keep at least one step).
  const tailKeep = Math.max(1, MAX_TRACE_STEPS - TRACE_HEAD_KEEP);
  return {
    steps: [...steps.slice(0, TRACE_HEAD_KEEP), ...steps.slice(-tailKeep)],
    omitted: steps.length - MAX_TRACE_STEPS,
  };
}
