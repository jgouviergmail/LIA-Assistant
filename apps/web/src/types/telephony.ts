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
  call_seconds: number | null;
  created_at: string;
  completed_at: string | null;
}
