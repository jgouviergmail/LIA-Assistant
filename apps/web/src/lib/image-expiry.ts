/**
 * Expiry of AI-generated images (N2) — the warning that used to be missing.
 *
 * A generated image is stored as an attachment with an `expires_at`, and a
 * scheduler deletes expired attachments every 6 hours
 * (`attachments_ttl_hours`, 24 h by default — `list_expired` does NOT filter
 * orphans, so a generated image really is purged). The chat showed a beautiful
 * image, a download button, and not a word about the fact that it disappears.
 *
 * The doctrine here is honesty over reassurance:
 *  - the deadline comes from the BACKEND, never from a hardcoded "24 h" — the
 *    TTL is configurable, so a constant in the UI would eventually lie;
 *  - a message with no `expires_at` (history predating N2) says NOTHING rather
 *    than guess;
 *  - once the deadline has passed the wording changes: claiming "available
 *    until yesterday 8pm" next to an image would be absurd.
 */

/** How the UI should talk about an image's lifetime. */
export type ImageExpiry =
  | { kind: 'unknown' }
  | { kind: 'expired' }
  | { kind: 'soon'; hoursLeft: number; at: Date }
  | { kind: 'later'; at: Date };

/** Below this many hours left, the warning becomes urgent. */
export const EXPIRY_SOON_HOURS = 6;

/**
 * Classify an image's remaining lifetime.
 *
 * Args:
 *   expiresAt: ISO-8601 instant from the backend, or nullish when unknown.
 *   now: Reference instant (injected — never read the clock in a pure module).
 *
 * Returns:
 *   The discriminated state the UI renders from. Unparseable input is treated
 *   as unknown: a malformed date must never produce "Invalid Date" on screen.
 */
export function classifyImageExpiry(expiresAt: string | null | undefined, now: Date): ImageExpiry {
  if (!expiresAt) return { kind: 'unknown' };

  const at = new Date(expiresAt);
  if (Number.isNaN(at.getTime())) return { kind: 'unknown' };

  const msLeft = at.getTime() - now.getTime();
  if (msLeft <= 0) return { kind: 'expired' };

  const hoursLeft = Math.ceil(msLeft / 3_600_000);
  return hoursLeft <= EXPIRY_SOON_HOURS ? { kind: 'soon', hoursLeft, at } : { kind: 'later', at };
}
