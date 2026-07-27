/**
 * Warning before the quota wall (A5).
 *
 * ## The defect
 *
 * The backend computes a graded status — `ok` / `warning` (≥80 % of a limit) /
 * `critical` (≥95 %) / `blocked_*` — and returns every dimension's usage plus
 * the cycle boundaries. The chat page read exactly TWO fields: `isBlocked` and
 * `blockReason`. Everything else was fetched, polled every 60 s, and thrown
 * away.
 *
 * The consequence is the worst possible shape for a limit: nothing, nothing,
 * nothing, then a wall. The user discovers the quota exists at the exact moment
 * they can no longer use the product, mid-task, with no idea when it lifts.
 *
 * ## What this decides
 *
 * Which dimension is the one about to run out (the binding one — the highest
 * percentage, since ANY dimension blocks the whole account), and how loudly to
 * say it. The rendering, wording and locale formatting stay in the component;
 * this module is pure so the rule itself can be tested exhaustively.
 */

import type { UserUsageLimitResponse, LimitDetail } from '@/types/usage-limits';

/** Dimensions that can bind, in the order the UI names them. */
export const USAGE_DIMENSIONS = [
  'cycle_tokens',
  'cycle_messages',
  'cycle_cost',
  'absolute_tokens',
  'absolute_messages',
  'absolute_cost',
] as const;

export type UsageDimension = (typeof USAGE_DIMENSIONS)[number];

/** What the chat should warn about, or `null` when there is nothing to say. */
export interface UsageWarning {
  /** `warning` ≥80 %, `critical` ≥95 % — mirrors the backend's own grading. */
  level: 'warning' | 'critical';
  /** The dimension closest to its limit — the one that will actually block. */
  dimension: UsageDimension;
  /** Rounded percentage of that dimension, 0-100. */
  usagePct: number;
  /** End of the billing cycle, when the dimension is a per-cycle one. */
  cycleEnd: string | null;
}

/** Percentage of a dimension, or null when it is unlimited/unknown. */
function pctOf(detail: LimitDetail | undefined): number | null {
  if (!detail || detail.usage_pct === null || detail.usage_pct === undefined) return null;
  return Number.isFinite(detail.usage_pct) ? detail.usage_pct : null;
}

/**
 * Decide the warning to show, if any.
 *
 * Args:
 *   limits: The `/usage-limits/me` payload, or null when the feature is off.
 *
 * Returns:
 *   The warning to render, or `null` when the user is fine — or ALREADY
 *   blocked, in which case the blocking banner says it better and a second
 *   message would just be noise.
 */
export function usageWarningOf(limits: UserUsageLimitResponse | null): UsageWarning | null {
  if (!limits) return null;
  // Blocked is not "almost blocked": the dedicated banner owns that state.
  if (limits.is_blocked) return null;
  if (limits.status !== 'warning' && limits.status !== 'critical') return null;

  // The binding dimension is the highest one: any single dimension blocks the
  // whole account, so warning about a lower one would name the wrong deadline.
  let worst: { dimension: UsageDimension; pct: number } | null = null;
  for (const dimension of USAGE_DIMENSIONS) {
    const pct = pctOf(limits[dimension]);
    if (pct === null) continue;
    if (!worst || pct > worst.pct) worst = { dimension, pct };
  }

  // Status says "warning" but no dimension reports a percentage: trust the
  // dimensions, not the label — a warning naming nothing is unactionable.
  if (!worst) return null;

  return {
    level: limits.status,
    dimension: worst.dimension,
    usagePct: Math.min(100, Math.round(worst.pct)),
    // Absolute limits do not reset with the cycle; promising a reset date for
    // one would be a lie.
    cycleEnd: worst.dimension.startsWith('cycle_') ? (limits.cycle_end ?? null) : null,
  };
}
