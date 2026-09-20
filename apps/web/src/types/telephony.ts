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
/**
 * What a call cost, cumulated — its live lookups, its synthesis, its relayed
 * turn under ONE run id — in the chat meter's own vocabulary.
 */
export interface TelephonyCallUsage {
  tokens_in: number;
  tokens_out: number;
  tokens_cache: number;
  cost_eur: number;
  google_api_requests: number;
}

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
  /** Which mandate the call ran under; `third_party` for every pre-lot-2 row. */
  call_kind: CallKind;
  /** The mode an owner call ran under (ADR-301); `direct` for every other call. */
  call_mode: PhoneCallMode;
  /** The call's cumulated bill (lot 8); absent or null while nothing was spent. */
  usage?: TelephonyCallUsage | null;
  /** How an owner call's words reached the chat, or why they did not; null otherwise. */
  relay_outcome: RelayOutcome | null;
}

/** Which mandate a call ran under — `CallKind` in the backend models. */
export type CallKind = 'third_party' | 'self' | 'verification';

/**
 * How a voice session's words reached the chat (`answered`, `waiting`), or
 * why they did not — the API's `RelayOutcome`, on a phone call or a direct
 * live session (ADR-301). A RUNTIME list, so the labels guard walks it and
 * the live card's fate vocabulary derives from it rather than copying it.
 * Null while the relay runs, and for every other kind of call.
 */
export const RELAY_OUTCOMES = [
  'answered',
  'waiting',
  'empty',
  'not_owner',
  'unanswered',
  'call_failed',
  'pending_question',
  'busy',
  'quota_blocked',
  'failed',
] as const;
export type RelayOutcome = (typeof RELAY_OUTCOMES)[number];

/**
 * How the person's own calls run (ADR-301): `delegated` — Live, the voice
 * hands every request to the chat, which acts in the conversation — or
 * `direct` — Live direct, the voice reads LIA's tools itself and the call is
 * relayed at its end. The stored vocabulary is the voice sessions'; the page
 * says « Live » / « Live direct ».
 */
export const PHONE_CALL_MODES = ['delegated', 'direct'] as const;
export type PhoneCallMode = (typeof PHONE_CALL_MODES)[number];

/**
 * The person's own phone identity — `TelephonyIdentityResponse`.
 *
 * The number is the person's own and travels whole: a masked number cannot be
 * checked for the typo that would send an owner call to a stranger.
 */
export interface TelephonyIdentity {
  phone_number: string | null;
  verified: boolean;
  verified_at: string | null;
  rich_context_enabled: boolean;
  /** The phone domains the person switched OFF for their own calls (lot 8). */
  disabled_domains: string[];
  /** Every domain the phone may read — the server's vocabulary, never guessed here. */
  available_domains: string[];
  verification_pending: boolean;
  /** The mode the person chose (ADR-301). */
  call_mode: PhoneCallMode;
  /** What a call placed now runs: the choice, or `direct` when Live is unavailable. */
  call_mode_effective: PhoneCallMode;
  /** Whether this instance can run a Live call (the vendor can call it back). */
  live_available: boolean;
  /** Why not, as a stable code this page translates; null when it can. */
  live_unavailable_reason: string | null;
}

/** What the page learns when the verification call leaves. */
export interface TelephonyIdentityVerifyStart {
  call_id: string | null;
  expires_in_seconds: number;
}
