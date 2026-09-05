/**
 * Hydrate what a turn performed from message metadata (ADR-263).
 *
 * The backend archives `[{label_key, values, status, tool_name}]` under
 * `message_metadata.performed_effects` — keys and values only, never a
 * translated sentence, so the wording follows the reader's language rather
 * than the one in use when the action happened. That is the same contract the
 * ⚙ execution trace follows, and the reason a message archived in French still
 * reads in German after a locale switch.
 *
 * Runs on every history row: malformed payloads degrade to `undefined` (no
 * block rendered) rather than throwing.
 */

import type { PerformedEffect, PerformedEffectStatus } from '@/types/performed-effects';
import { MAX_DISPLAYED_EFFECTS } from '@/types/performed-effects';

/** Metadata key written by the backend (`FIELD_PERFORMED_EFFECTS`). */
const PERFORMED_EFFECTS_METADATA_KEY = 'performed_effects';

/** The only statuses a bubble states: a refusal changed nothing. */
const DISPLAYED_STATUSES: ReadonlySet<string> = new Set<PerformedEffectStatus>([
  'succeeded',
  'failed',
]);

function hydrateValues(raw: unknown): Record<string, string | number> {
  if (typeof raw !== 'object' || raw === null) return {};
  const values: Record<string, string | number> = {};
  for (const [key, value] of Object.entries(raw as Record<string, unknown>)) {
    if (typeof value === 'string' || typeof value === 'number') values[key] = value;
  }
  return values;
}

function hydrateEffect(raw: unknown): PerformedEffect | null {
  if (typeof raw !== 'object' || raw === null) return null;
  const effect = raw as Record<string, unknown>;
  const labelKey = effect.label_key;
  const status = effect.status;
  if (typeof labelKey !== 'string' || !labelKey) return null;
  if (typeof status !== 'string' || !DISPLAYED_STATUSES.has(status)) return null;
  return {
    labelKey,
    values: hydrateValues(effect.values),
    status: status as PerformedEffectStatus,
    toolName: typeof effect.tool_name === 'string' ? effect.tool_name : '',
  };
}

/**
 * Build the performed-effect list from persisted message metadata, if any.
 *
 * @param metadata - The message's `message_metadata` payload.
 * @returns The effects to display, or `undefined` when the metadata carries
 *   none (absent, malformed, or nothing displayable).
 */
export function performedEffectsFromMetadata(
  metadata: Record<string, unknown> | null | undefined
): PerformedEffect[] | undefined {
  if (!metadata) return undefined;
  const raw = metadata[PERFORMED_EFFECTS_METADATA_KEY];
  if (!Array.isArray(raw)) return undefined;

  const effects = raw
    .map(hydrateEffect)
    .filter((effect): effect is PerformedEffect => effect !== null)
    .slice(0, MAX_DISPLAYED_EFFECTS);

  return effects.length > 0 ? effects : undefined;
}
