/**
 * The consultation register, as the API serves it (ADR-263, lot 4).
 *
 * The companion of `types/effects.ts`, and deliberately narrower. A treatment
 * row records WHICH capability answered, WHEN, HOW LONG it took and WITH WHAT
 * outcome — never what was asked. "Searched Marie's emails" would reveal a
 * search nobody asked to have recorded, where "sent an email to Marie" records
 * an act the user requested.
 *
 * The payload carries a `domain` KEY, not a sentence: the wording is resolved
 * client-side under `treatments.domains.*`, so a journal opened in German reads
 * in German about a consultation made while the interface was in French.
 */

/** What was observed. There is nothing else to say about a read. */
export type TreatmentOutcome = 'ok' | 'failed';

/** Where the authority for the turn came from — same vocabulary as the ledger. */
export type TreatmentSource = 'user' | 'scheduled' | 'subagent';

export interface TreatmentEntry {
  /** Register row id — the React key, and the deduplication key across pages. */
  id: string;
  /** Domain key resolved under `treatments.domains.*` (never a raw tool name). */
  domain: string;
  /** Capability consulted — the technical half, shown beside the domain. */
  tool_name: string;
  /** Its declared policy, or null for a capability that declares none. */
  mutation_policy: string | null;
  outcome: TreatmentOutcome;
  source: TreatmentSource;
  execution_mode: string;
  /** Wall-clock duration of the call. */
  duration_ms: number;
  /** Conversation the consultation belongs to. */
  thread_id: string;
  /** Turn that consulted. */
  run_id: string;
  /** When the call returned (UTC). */
  occurred_at: string;
}

export interface TreatmentPage {
  entries: TreatmentEntry[];
  /** EXACT number of consultations matching the filter (ADR-185). */
  total: number;
  limit: number;
  offset: number;
}
