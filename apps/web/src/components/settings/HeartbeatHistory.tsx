'use client';

import { useTranslation } from 'react-i18next';

import { priorityTone } from '@/lib/status-tone';

import {
  NotificationHistoryList,
  type NotificationHistoryRow,
} from '@/components/settings/NotificationHistoryList';
import {
  HEARTBEAT_HISTORY_PAGE_SIZE,
  type HeartbeatNotification,
} from '@/hooks/useHeartbeatHistory';

/**
 * The proactive notifications this account actually received.
 *
 * The panel showed the configuration and never its output: `GET
 * /heartbeat/history` had shipped with the domain and no client ever called
 * it, so a reader could tune frequency and sources without ever seeing what
 * LIA had chosen to say — or judging whether it was worth being interrupted
 * for.
 *
 * Presentational by design: the caller owns the fetch, so the loading and
 * error shapes are props rather than a second data path. The card itself is
 * `NotificationHistoryList`, shared with the interest history — the two answer
 * the same question and must not drift into two visual languages.
 */
export interface HeartbeatHistoryProps {
  /** Undefined until the first response lands. */
  notifications: HeartbeatNotification[] | undefined;
  /** EXACT count over the whole set, not this page (ADR-185). */
  total: number;
  /** True only before the first payload — never on a refetch. */
  firstLoad: boolean;
  loading: boolean;
  error: Error | null;
  /** BCP-47 locale for date formatting. */
  locale: string;
}

/** Canonical backend labels, in the order the decision prompt lists them. */
const KNOWN_SOURCES = new Set([
  'UPCOMING_CALENDAR_EVENTS',
  'PENDING_TASKS',
  'UNREAD_EMAILS',
  'CURRENT_WEATHER',
  'WEATHER_CHANGES',
  'USER_INTERESTS',
  'USER_MEMORIES',
  'JOURNAL_ENTRIES',
  'HEALTH_SIGNALS',
  'UPCOMING_BIRTHDAYS',
  'OPEN_LOOPS',
  'DEPARTURE_ADVICE',
]);

/** The three the column is documented to hold — it is a plain string, not an
 *  enum, so a fourth is possible and must not surface as a missing i18n key.
 *  Its TONE is decided by `priorityTone`, which stays neutral for an unknown
 *  level rather than guessing at its urgency. */
const KNOWN_PRIORITIES = new Set(['high', 'medium', 'low']);

export function HeartbeatHistory({
  notifications,
  total,
  firstLoad,
  loading,
  error,
  locale,
}: HeartbeatHistoryProps) {
  const { t } = useTranslation();

  const rows: NotificationHistoryRow[] | undefined = notifications?.map(item => ({
    id: item.id,
    createdAt: item.created_at,
    content: item.content,
    badge: {
      // Raw rather than a missing key, exactly like the source labels below:
      // a priority the backend adds later must not read as
      // `heartbeat.history.priority_X` on screen.
      label: KNOWN_PRIORITIES.has(item.priority)
        ? t(`heartbeat.history.priority_${item.priority}`)
        : item.priority,
      tone: priorityTone(item.priority),
    },
    chips: item.sources_used.map(source => ({
      key: source,
      // An unknown label renders RAW rather than as a missing i18n key: a new
      // backend source must never surface as `heartbeat.history.source_X` in
      // the interface.
      label: KNOWN_SOURCES.has(source) ? t(`heartbeat.history.source_${source}`) : source,
    })),
    feedback: item.user_feedback,
  }));

  return (
    <NotificationHistoryList
      rows={rows}
      firstLoad={firstLoad}
      loading={loading}
      error={error}
      locale={locale}
      labels={{
        empty: t('heartbeat.history.empty'),
        error: t('heartbeat.history.error'),
        count: t('heartbeat.history.count', {
          shown: notifications?.length ?? 0,
          total,
          page: HEARTBEAT_HISTORY_PAGE_SIZE,
        }),
      }}
    />
  );
}
