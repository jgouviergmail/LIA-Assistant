/**
 * Sharing a generated image with a connection (ADR-316) — the pure half.
 *
 * The chat card and the gallery both offer the action; what they need to know
 * lives here once: which attachment an image card points at, whether the
 * instance offers connections at all, and the bound the comment obeys.
 */

import type { AppConfig } from '@/hooks/useAppConfig';

/** Mirror of the backend `PEERS_IMAGE_SHARE_COMMENT_MAX_CHARS` (pinned by a backend test). */
export const IMAGE_SHARE_COMMENT_MAX_CHARS = 500;

/** `/api/v1/attachments/{uuid}` — relative, or absolute once resolved against the API origin. */
const ATTACHMENT_URL =
  /\/api\/v1\/attachments\/([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})(?=[/?#]|$)/i;

/**
 * The attachment an image card shows, read from its URL.
 *
 * @param url - The card's URL as the API emitted it.
 * @returns The attachment id, or null for anything that is not one of our
 *   attachments (an external image cannot be shared).
 */
export function attachmentIdFromUrl(url: string): string | null {
  return ATTACHMENT_URL.exec(url)?.[1] ?? null;
}

/**
 * Whether connections are offered on this instance — the EFFECTIVE state.
 *
 * The capability map carries the operator's switch as well as the deployment
 * ceiling; an older API that omits it falls back to the ceiling alone.
 *
 * @param config - The app configuration, or null while it loads.
 * @returns True when a share could reach a connection.
 */
export function peersAvailable(config: AppConfig | null): boolean {
  const capability = config?.capabilities?.peers;
  return capability ? capability.enabled : Boolean(config?.features?.peers_enabled);
}
