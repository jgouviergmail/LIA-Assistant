'use client';

import { useTranslation } from 'react-i18next';

import {
  NotificationHistoryList,
  type NotificationHistoryRow,
} from '@/components/settings/NotificationHistoryList';
import {
  INTEREST_HISTORY_PAGE_SIZE,
  type InterestNotification,
} from '@/hooks/useInterestNotificationHistory';

/**
 * The interest notifications this account actually received.
 *
 * Same blind spot the proactive history closed, on the same page: the panel
 * let the reader tune topics and frequency without ever showing what those
 * settings produced. The card is literally the proactive one
 * (`NotificationHistoryList`) — two panels answering the same question must
 * not drift into two visual languages.
 *
 * Two differences of VOCABULARY, not of shape:
 *
 * - no priority badge: an interest nudge is never urgent, and inventing a
 *   level to fill the slot would state something the backend never decided;
 * - the chips name the interest and the provider that produced the item,
 *   where the proactive card names the context sources it combined.
 */
export interface InterestNotificationHistoryProps {
  /** Undefined until the first response lands. */
  notifications: InterestNotification[] | undefined;
  /** EXACT count over the whole set, not this page (ADR-185). */
  total: number;
  /** True only before the first payload — never on a refetch. */
  firstLoad: boolean;
  loading: boolean;
  error: Error | null;
  /** BCP-47 locale for date formatting. */
  locale: string;
}

/** Providers this build can name. Unknown ones render raw, never as a key. */
const KNOWN_SOURCES = new Set(['perplexity', 'brave', 'rss', 'web']);

export function InterestNotificationHistory({
  notifications,
  total,
  firstLoad,
  loading,
  error,
  locale,
}: InterestNotificationHistoryProps) {
  const { t } = useTranslation();

  const rows: NotificationHistoryRow[] | undefined = notifications?.map(item => ({
    id: item.id,
    createdAt: item.created_at,
    // Null for every row written before the audit table started keeping the
    // message (2026-08-03). The card then shows the date, the interest and the
    // verdict without a paragraph — no backfill is possible, a hash does not
    // invert, and an invented summary would be worse than an absent one.
    content: item.content,
    // The badge slot, where the proactive card puts its priority. Interests
    // have no priority — but they have a SUBJECT, which is what the reader
    // recognises the notification by. Leaving the slot empty made the interest
    // row visibly lighter than its neighbour on the same page, for two
    // vocabularies that should read alike.
    //
    // Absent when the interest has since been deleted: a fact about the
    // account, and not a reason to hide the row from an audit.
    badge: item.topic
      ? { label: item.topic, className: 'bg-primary/10 text-primary' }
      : null,
    chips: [
      {
        key: `source:${item.source}`,
        label: KNOWN_SOURCES.has(item.source)
          ? t(`interests.history.source_${item.source}`)
          : item.source,
      },
    ],
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
        empty: t('interests.history.empty'),
        error: t('interests.history.error'),
        count: t('interests.history.count', {
          shown: notifications?.length ?? 0,
          total,
          page: INTEREST_HISTORY_PAGE_SIZE,
        }),
      }}
    />
  );
}
