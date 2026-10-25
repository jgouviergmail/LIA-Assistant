/**
 * What a tool step did, added up per label (owner request 2026-10-24).
 *
 * The stream says, per ReAct call, `started` then `completed` or `failed` under
 * the call's `step_key` — the read's counts on the finish — and, per pipeline
 * tool, one total without a key. The bubble shows ONE line per label, so the
 * calls are added up here: a call counted once by its key (its latest outcome
 * kept), a pipeline total taken as it comes. The server's persisted trace adds
 * them up by the same rule (`streaming/trace_capture._Tally`).
 */

/** Counts only: what a step did, never words (the trace is persisted). */
export interface StepOutcome {
  calls?: number;
  found?: number;
  shown?: number;
  failed?: number;
}

export interface StepTally {
  /** Each call's latest outcome, by its `step_key`. */
  calls: Map<string, StepOutcome>;
  /** A pipeline's per-tool total (keyless). */
  bulk: StepOutcome;
}

const OUTCOME_KEYS = ['calls', 'found', 'shown', 'failed'] as const;

/** The known counts of a raw outcome: non-negative integers only. */
export function outcomeCounts(raw: unknown): StepOutcome {
  if (typeof raw !== 'object' || raw === null) return {};
  const source = raw as Record<string, unknown>;
  const counts: StepOutcome = {};
  for (const key of OUTCOME_KEYS) {
    const value = source[key];
    if (typeof value === 'number' && Number.isInteger(value) && value >= 0) counts[key] = value;
  }
  return counts;
}

export function newTally(): StepTally {
  return { calls: new Map(), bulk: {} };
}

export function addToTally(tally: StepTally, stepKey: string | undefined, outcome: unknown): void {
  const counts = outcomeCounts(outcome);
  if (stepKey) tally.calls.set(stepKey, counts);
  else if (Object.keys(counts).length > 0) tally.bulk = counts;
}

/** The counts worth showing; empty when the steps only say they ran. */
export function summarizeTally(tally: StepTally): StepOutcome {
  const calls = [...tally.calls.values()];
  const sum = (pick: (outcome: StepOutcome) => number) =>
    calls.reduce((total, outcome) => total + pick(outcome), 0);
  const found = sum(o => o.found ?? 0) + (tally.bulk.found ?? 0);
  const shown = sum(o => o.shown ?? o.found ?? 0) + (tally.bulk.found ?? 0);
  const failed = sum(o => o.failed ?? 0) + (tally.bulk.failed ?? 0);
  const callCount = calls.length + (tally.bulk.calls ?? 0);
  const summary: StepOutcome = callCount > 1 ? { calls: callCount } : {};
  if (found > 0) {
    summary.found = found;
    if (shown < found) summary.shown = shown;
  }
  if (failed > 0) summary.failed = failed;
  return summary;
}

type Translate = (key: string, options?: Record<string, unknown>) => string;

/**
 * A label once its step says what it did: the trailing ellipsis that
 * announced work in progress goes (« Récupération des e-mails… — 12 résultats »
 * read as still running).
 */
export function settledLabel(label: string): string {
  return label.replace(/\s*(?:\.\.\.|…)$/u, '');
}

/** The counts in words, joined — '' when there is nothing to say. */
export function outcomeText(t: Translate, outcome: StepOutcome | undefined): string {
  if (!outcome) return '';
  return OUTCOME_KEYS.filter(key => outcome[key] !== undefined)
    .map(key => t(`execution.outcome.${key}`, { count: outcome[key] }))
    .join(t('execution.outcome.joiner'));
}
