/**
 * The effect register, as the API serves it (ADR-263).
 *
 * The payload carries `label_key` + `values` rather than a sentence: the
 * wording is resolved client-side, in the reader's current language. That is
 * why a journal opened in German reads in German about an action taken while
 * the interface was in French.
 */

/** Outcome of a recorded effect, exactly as the ledger stores it. */
export type EffectStatus = 'succeeded' | 'failed' | 'refused' | 'claimed' | 'abandoned';

/** Where the authority to act came from. */
export type EffectSource = 'user' | 'scheduled' | 'subagent';

export interface EffectEntry {
  /** Ledger row id — the React key, and the deduplication key across pages. */
  id: string;
  /** i18n key under `effects.labels.*`. */
  label_key: string;
  /** Values the wording interpolates. */
  values: Record<string, string | number>;
  /** Capability that acted (admin-facing detail, never shown to a user). */
  tool_name: string;
  /** Declared policy under which it acted. */
  mutation_policy: string;
  status: EffectStatus;
  source: EffectSource;
  execution_mode: string;
  /** How the user authorised it, when they did. */
  approval_kind: string | null;
  /** Why it failed or was refused. */
  error_code: string | null;
  /** When it was claimed — before it happened. */
  claimed_at: string;
  /** When its outcome was recorded. */
  closed_at: string | null;
}

export interface EffectPage {
  entries: EffectEntry[];
  /** EXACT number of effects, not the length of this page (ADR-185). */
  total: number;
  limit: number;
  offset: number;
}
