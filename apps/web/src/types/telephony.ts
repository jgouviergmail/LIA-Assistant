/**
 * Outbound agentic calls — the frontend contract (A6).
 *
 * Mirrors `TelephonyCallSummary` (`apps/api/src/domains/telephony/schemas.py`),
 * the public view of a call. The backend deliberately OMITS the callee's phone
 * number (encrypted at rest, never exposed), so this type has no field for it
 * and no code can accidentally surface one.
 */

/** Lifecycle of a call — `PhoneCallStatus` in the backend models. */
export type PhoneCallStatus =
  | 'dialing'
  | 'in_progress'
  | 'completed'
  | 'no_answer'
  | 'voicemail'
  | 'failed'
  | 'cancelled';

/** Semantic result of a completed call, set by the return synthesis. */
export type PhoneCallOutcome = 'objective_met' | 'partial' | 'declined' | 'unreachable';

/** Statuses during which the call is still happening. */
export const ACTIVE_CALL_STATUSES: readonly PhoneCallStatus[] = ['dialing', 'in_progress'];

/**
 * T01 structured debrief — OUR synthesis output (key points, commitments,
 * follow-ups, draft, uncertainties). Every list may be empty; the whole object
 * is null for pre-T01 calls, empty outcomes, and once the retention reaper
 * purges. `key_points` carries the structured FINDINGS of an information call.
 */
export interface PhoneCallDebrief {
  key_points?: string[];
  commitments?: string[];
  follow_up_tasks?: string[];
  follow_up_reminders?: string[];
  follow_up_draft?: string | null;
  uncertainties?: string[];
}

/** Runtime check — the debrief travels as untyped notification metadata. */
export function isPhoneCallDebrief(value: unknown): value is PhoneCallDebrief {
  if (!value || typeof value !== 'object') return false;
  const candidate = value as Record<string, unknown>;
  const listKeys = [
    'key_points',
    'commitments',
    'follow_up_tasks',
    'follow_up_reminders',
    'uncertainties',
  ] as const;
  return listKeys.every(
    key =>
      candidate[key] === undefined ||
      (Array.isArray(candidate[key]) &&
        (candidate[key] as unknown[]).every(item => typeof item === 'string'))
  );
}

/**
 * The typed facts the post-call synthesis extracted, as the backend publishes
 * them.
 *
 * All optional: a call may yield none of them. Everything here is what the
 * OTHER party said or proposed — a date, a place, a price, an option left
 * open. None of it is a decision the assistant took, and none of it may become
 * one without the user saying so.
 */
export interface StructuredCallData {
  /** Did the callee agree to the ask? Null when the call did not settle it. */
  agreed?: boolean | null;
  /** ISO-8601 datetime PROPOSED on the call — never one that was booked. */
  proposed_datetime?: string | null;
  /** Place proposed or agreed. */
  location?: string | null;
  /** Short free-text note. */
  notes?: string | null;
  /** Any extra cost, surcharge or fee mentioned, with its amount. */
  additional_costs?: string | null;
  /** What the assistant deliberately did NOT accept, left for the user. */
  pending_user_decision?: string | null;
}

/** One call, as `GET /telephony/calls` returns it (newest first). */
export interface TelephonyCallSummary {
  id: string;
  /** Human-readable callee name — never the number. */
  callee_display: string;
  /** What LIA was asked to accomplish. */
  objective: string;
  status: PhoneCallStatus;
  outcome: PhoneCallOutcome | null;
  /** Factual recap; null while in flight, and again once the transcript is purged. */
  summary: string | null;
  /** T01 structured debrief; null before T01 and once purged. */
  debrief: PhoneCallDebrief | null;
  /** Typed facts extracted from the call; null before completion and once purged. */
  structured_data?: StructuredCallData | null;
  call_seconds: number | null;
  created_at: string;
  completed_at: string | null;
}
