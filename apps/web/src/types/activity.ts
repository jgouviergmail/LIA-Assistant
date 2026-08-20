/**
 * Activity timeline types — mirror of the backend schemas
 * (`apps/api/src/domains/activity/schemas.py`, Lot 1-A1).
 *
 * `kind` is a stable identifier resolved to a localized label client-side
 * (label_key doctrine); `text` is the user's own persisted content.
 */

/** Stable event kinds — keep in sync with backend `ALL_ACTIVITY_KINDS`. */
export const ACTIVITY_KINDS = [
  'heartbeat_notification',
  'interest_notification',
  'journal_entry',
  'habit_detected',
  'open_loop_created',
  'open_loop_closed',
  'scheduled_action_run',
] as const;

export type ActivityKind = (typeof ACTIVITY_KINDS)[number];

export interface ActivityEvent {
  kind: string;
  ref_id: string;
  /** ISO-8601 UTC timestamp. */
  occurred_at: string;
  text: string | null;
  status: string | null;
}

export interface ActivityKindTotal {
  kind: string;
  /** Exact COUNT(*) over the whole window (ADR-185: exact or absent). */
  total: number;
  /** True when the per-source cap dropped rows from the pageable pool. */
  truncated: boolean;
}

export interface ActivityTimelineResponse {
  events: ActivityEvent[];
  totals: ActivityKindTotal[];
  has_more: boolean;
  offset: number;
  limit: number;
  window_days: number;
  failed_kinds: string[];
}
