/**
 * What a turn actually performed, as recorded in the effect register (ADR-263).
 *
 * These are not the ⚙ execution steps: a step says what the assistant DID
 * internally, an effect says what changed in the world — an email that left, a
 * light that switched, a task that closed. The register records it before it
 * happens and closes it from the result, so the line under a bubble states a
 * fact rather than an intention.
 *
 * The backend ships `label_key` + `values`, never a sentence, so the wording
 * follows the reader's current language rather than the one in use when the
 * action happened.
 */

/** Outcome of one recorded effect. Only these two are ever displayed. */
export type PerformedEffectStatus = 'succeeded' | 'failed';

export interface PerformedEffect {
  /** i18n key under `effects.labels.*`, resolved client-side. */
  labelKey: string;
  /** Values the wording interpolates (recipient, target, count…). */
  values: Record<string, string | number>;
  /** Whether the effect went through. */
  status: PerformedEffectStatus;
  /** Registered capability that acted — shown to admins, never to a user. */
  toolName: string;
}

/**
 * A bubble states what happened; it is not an audit page.
 *
 * Past this many effects the list is capped and the journal takes over, the
 * same way the execution trace caps its steps.
 */
export const MAX_DISPLAYED_EFFECTS = 6;
