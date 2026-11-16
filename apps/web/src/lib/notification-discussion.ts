/**
 * Which discussion a notification went to, when it is not the one on screen.
 *
 * The return of an act comes back to the discussion it was begun in (ADR-378
 * amendment 2026-11-14): a call placed from an annex, a meeting imported there.
 * The server names that discussion in the live event's metadata
 * (`conversation_id`) only when it is an annex — a notification naming none
 * went to Main. A toast shown elsewhere says where the message is, Main
 * included, and offers to open it.
 */

import type { ConversationCataloguePage } from '@/types/conversation';

/**
 * What the person calls a discussion of the catalogue on hand.
 *
 * @param page - The switcher's catalogue page, when it was read.
 * @param id - The discussion a notification named.
 * @param mainLabel - Main's translated name.
 * @returns Main's name, an annex's title, or `null` when the page does not
 *   hold the discussion or the annex has no title yet.
 */
export function discussionTitleIn(
  page: ConversationCataloguePage | undefined,
  id: string,
  mainLabel: string
): string | null {
  const row = page?.items.find(item => item.id === id);
  if (row === undefined) return null;
  return row.kind === 'main' ? mainLabel : row.title;
}

/** Where a notification landed, when it is not the discussion on screen. */
export type NotificationPlace =
  | { readonly kind: 'main' }
  | { readonly kind: 'discussion'; readonly id: string };

/** The discussion on screen, as the chat knows it. */
export interface ShownDiscussion {
  /** Its id (`null` while Main's record is unknown). */
  readonly id: string | null;
  /** Whether it is Main. */
  readonly isMain: boolean;
}

/**
 * Where a notification landed, when it differs from the discussion shown.
 *
 * @param metadata - The live event's metadata.
 * @param shown - The discussion on screen.
 * @returns The discussion the notification named, Main for one naming none
 *   seen from an annex, or `null` when it is about the discussion on screen.
 */
export function notificationElsewhere(
  metadata: Record<string, unknown> | undefined,
  shown: ShownDiscussion
): NotificationPlace | null {
  const target = metadata?.conversation_id;
  if (typeof target === 'string' && target.length > 0) {
    return target === shown.id ? null : { kind: 'discussion', id: target };
  }
  // The server names an annex alone: a notification naming none went to Main.
  return shown.isMain ? null : { kind: 'main' };
}
