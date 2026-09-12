/**
 * What the advertised demonstrator offers, as the link payload carries it.
 *
 * `GET /api/v1/product/public-demo-link` relays, beside the link, the
 * `capabilities` block the demonstrator publishes on its own `/config` —
 * every capability of the registry with its effective state, keyed by the
 * same vocabulary the locale files translate (`capabilities.items.<key>`).
 * The relay is server-side on purpose: the document's CSP allows
 * `connect-src` to this instance's API alone (ADR-098), so the page could
 * not ask the demonstrator itself (measured 2026-09-12 in the hermetic
 * browser suite).
 *
 * `null` is a state of its own — "the demonstrator did not answer" — and is
 * never rendered as an empty "switched off" list.
 */

/** One capability as the demonstrator describes it. */
export interface PublicCapabilityState {
  enabled: boolean;
  family: string;
}

/** The relayed block, keyed by capability. */
export type PublicCapabilities = Record<string, PublicCapabilityState>;

function isCapabilityState(value: unknown): value is PublicCapabilityState {
  return (
    typeof value === 'object' &&
    value !== null &&
    typeof (value as PublicCapabilityState).enabled === 'boolean' &&
    typeof (value as PublicCapabilityState).family === 'string'
  );
}

/** Narrow an untrusted `capabilities` field to the well-formed entries, or null. */
export function readPublicCapabilities(block: unknown): PublicCapabilities | null {
  if (typeof block !== 'object' || block === null) return null;
  const entries = Object.entries(block as Record<string, unknown>).filter(
    (entry): entry is [string, PublicCapabilityState] => isCapabilityState(entry[1])
  );
  return entries.length > 0 ? Object.fromEntries(entries) : null;
}
