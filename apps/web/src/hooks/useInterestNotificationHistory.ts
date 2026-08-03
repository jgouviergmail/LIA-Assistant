'use client';

import { useApiQuery } from './useApiQuery';

/**
 * One delivered interest notification, as the audit trail recorded it.
 *
 * Deliberately the same shape as `HeartbeatNotification` minus what interests
 * do not have: no priority (an interest nudge is never urgent) and a single
 * content provider rather than a list of context sources.
 */
export interface InterestNotification {
  id: string;
  created_at: string;
  /**
   * The message that was sent.
   *
   * Optional because the audit table only started keeping it on 2026-08-03:
   * it stored a SHA-256 hash for deduplication and dropped the text. An older
   * row renders without its paragraph rather than with an invented one, and no
   * backfill is possible — a hash does not invert.
   */
  content: string | null;
  /** Content provider that produced it, e.g. `perplexity`. */
  source: string;
  /** The interest it was about; null when that interest has been deleted. */
  topic: string | null;
  /** `thumbs_up` | `thumbs_down` | `block`, or null when never rated. */
  user_feedback: string | null;
}

export interface InterestNotificationHistory {
  notifications: InterestNotification[];
  /**
   * Exact count over the WHOLE set, not the length of this page.
   *
   * The backend counts with an aggregate and pages the rows separately, so
   * "the last N of M" is a claim rather than an approximation (ADR-185).
   */
  total: number;
}

/** How many rows the settings panel shows — the same as the proactive one. */
export const INTEREST_HISTORY_PAGE_SIZE = 10;

/**
 * The interest notifications actually delivered to this account.
 *
 * Same blind spot the proactive history closed: the panel let the reader tune
 * frequency and topics without ever showing what those settings produced.
 *
 * @param enabled - Fetch only when the section is open; a collapsed panel must
 *   not pay for a list nobody is looking at.
 */
export function useInterestNotificationHistory(enabled = true) {
  const { data, loading, error, refetch } = useApiQuery<InterestNotificationHistory>(
    `/interests/notifications/history?limit=${INTEREST_HISTORY_PAGE_SIZE}`,
    { componentName: 'useInterestNotificationHistory', enabled }
  );

  return {
    notifications: data?.notifications,
    total: data?.total ?? 0,
    // Derived from `data`, never from `error`: a refetch clears the error, and
    // a spinner keyed on it would unmount the list mid-refresh.
    firstLoad: data === undefined && loading,
    loading,
    error,
    refetch,
  };
}
