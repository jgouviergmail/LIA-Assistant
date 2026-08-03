'use client';

import { useApiQuery } from './useApiQuery';

/**
 * One delivered proactive notification, as the audit trail recorded it.
 *
 * `id` is the notification's primary key AND the identifier its archived chat
 * card carries, so the feedback route resolves the same row from either
 * surface (ADR-196).
 */
export interface HeartbeatNotification {
  id: string;
  created_at: string;
  content: string;
  /** Canonical source labels, e.g. `UPCOMING_CALENDAR_EVENTS`. */
  sources_used: string[];
  /** `low` | `medium` | `high`. */
  priority: string;
  /** `thumbs_up` | `thumbs_down`, or null when never rated. */
  user_feedback: string | null;
}

export interface HeartbeatHistory {
  notifications: HeartbeatNotification[];
  /**
   * Exact count over the WHOLE set, not the length of this page.
   *
   * The backend counts with an aggregate and pages the rows separately, so
   * "the last N of M" is a claim rather than an approximation (ADR-185).
   */
  total: number;
}

/** How many rows the settings panel shows. */
export const HEARTBEAT_HISTORY_PAGE_SIZE = 10;

/**
 * The proactive notifications actually delivered to this account.
 *
 * The endpoint has existed since the domain shipped and nothing consumed it:
 * the panel showed the configuration and never what it produced, so there was
 * no way to see — or judge — what LIA had chosen to say.
 */
export function useHeartbeatHistory(enabled = true) {
  const { data, loading, error, refetch } = useApiQuery<HeartbeatHistory>(
    `/heartbeat/history?limit=${HEARTBEAT_HISTORY_PAGE_SIZE}`,
    { componentName: 'useHeartbeatHistory', enabled }
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
