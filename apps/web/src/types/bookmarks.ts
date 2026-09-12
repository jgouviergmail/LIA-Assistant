/**
 * The answers a person kept, as the tab and the bubble read them (ADR-282).
 *
 * The wire shapes mirror `domains/bookmarks/schemas.py` exactly: a backend
 * guard reads this file, because a field spelled two ways is how a card
 * behaves differently live and after a reload.
 */

/** One kept answer. */
export interface Bookmark {
  id: string;
  /** The archived message while it exists; null once the conversation is gone. */
  message_id: string | null;
  /** The conversation while it exists; null once it is gone. */
  conversation_id: string | null;
  /** The answer, verbatim: markdown or a `lia-response` HTML document. */
  content: string;
  /** The person's request that produced the answer; null when none did. */
  request_content: string | null;
  /** When the answer was written (UTC, ISO-8601). */
  answered_at: string;
  /** When the answer was kept (UTC, ISO-8601). */
  created_at: string;
}

/** One page, its EXACT total (ADR-185) and the bounds the API enforces. */
export interface BookmarkList {
  items: Bookmark[];
  total: number;
  limit: number;
  offset: number;
  /** Largest page the API serves — published because it is enforced (ADR-184). */
  max_limit: number;
  /** How many bookmarks the account may keep — published because it is enforced. */
  max_per_user: number;
}

/** What every bubble needs to draw its toggle. */
export interface BookmarkState {
  /** `message_id → bookmark_id`, for every bookmark still attached to a message. */
  message_ids: Record<string, string>;
}

/** What the bubble sends. */
export interface BookmarkKeepRequest {
  message_id: string;
}
