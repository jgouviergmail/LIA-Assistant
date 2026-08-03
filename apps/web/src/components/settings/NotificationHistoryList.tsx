'use client';

import { AlertCircle, ThumbsDown, ThumbsUp } from 'lucide-react';
import { useTranslation } from 'react-i18next';

import { LoadingSpinner } from '@/components/ui/loading-spinner';
import { cn } from '@/lib/utils';

/**
 * The shared card of a delivered-notification history.
 *
 * Two panels show one: the proactive notifications and the interest ones. They
 * answer the same question — "what was I interrupted with, and was it worth
 * it?" — so they share this shell rather than two implementations that drift
 * into two visual languages the day one of them is touched.
 *
 * What each caller supplies is the VOCABULARY (which chips, which emphasis,
 * which wording); what lives here is the shape, the ordering of states and the
 * three rules that were got wrong once already:
 *
 * - the error is checked BEFORE emptiness — "nothing yet" on a failed fetch
 *   tells the reader their assistant has been silent, which may be false;
 * - the first-load spinner is keyed on the absence of data, never on `error`
 *   (a refetch clears it and would unmount the list mid-refresh);
 * - the count states the whole set next to the page, so a cap is stated rather
 *   than applied in silence (ADR-185).
 */

/** One row, already reduced to what the card draws. */
export interface NotificationHistoryRow {
  id: string;
  /** ISO-8601 UTC — the `dateTime` attribute and the sort key. */
  createdAt: string;
  /** The message, when it was kept. Absent renders no paragraph, never a blank. */
  content: string | null;
  /** Emphasised marker (a priority, a state) — at most one. */
  badge?: { label: string; className: string } | null;
  /** Neutral chips: the sources used, the interest, the provider. */
  chips: { key: string; label: string }[];
  /** `thumbs_up` | `thumbs_down` | anything else, or null when never rated. */
  feedback: string | null;
}

export interface NotificationHistoryListProps {
  /** Undefined until the first response lands. */
  rows: NotificationHistoryRow[] | undefined;
  /** True only before the first payload — never on a refetch. */
  firstLoad: boolean;
  loading: boolean;
  error: Error | null;
  /** BCP-47 locale for date formatting. */
  locale: string;
  /** Already translated by the caller — this shell resolves no keys of its own. */
  labels: { empty: string; error: string; count: string };
}

export function NotificationHistoryList({
  rows,
  firstLoad,
  loading,
  error,
  locale,
  labels,
}: NotificationHistoryListProps) {
  if (firstLoad) {
    return (
      <div className="flex justify-center py-6">
        <LoadingSpinner className="h-5 w-5" />
      </div>
    );
  }

  // Checked BEFORE emptiness: a failed fetch that renders "nothing yet" tells
  // the reader their assistant has been silent, which may be false.
  if (error && !rows) {
    return (
      <p role="alert" className="text-sm text-destructive">
        {labels.error}
      </p>
    );
  }

  if (!rows?.length) {
    return <p className="text-sm italic text-muted-foreground">{labels.empty}</p>;
  }

  // Built ONCE per render, not once per row: `Intl.DateTimeFormat` is
  // expensive to construct and identical for every line of the list.
  let formatter: Intl.DateTimeFormat | null = null;
  try {
    formatter = new Intl.DateTimeFormat(locale, { dateStyle: 'medium', timeStyle: 'short' });
  } catch {
    // An unusable locale must not blank the history — the raw instant is
    // worse-looking and still true.
    formatter = null;
  }
  const formatDate = (iso: string) => {
    if (!formatter) return iso;
    try {
      return formatter.format(new Date(iso));
    } catch {
      return iso;
    }
  };

  return (
    <div className="space-y-2">
      <ul className="space-y-2" role="list" aria-busy={loading || undefined}>
        {rows.map(row => (
          <li
            key={row.id}
            className="space-y-1.5 rounded-lg border border-border/40 bg-card/40 px-3 py-2"
          >
            <div className="flex flex-wrap items-center gap-2">
              <time dateTime={row.createdAt} className="text-xs tabular-nums text-muted-foreground">
                {formatDate(row.createdAt)}
              </time>
              {row.badge && (
                <span
                  className={cn(
                    'rounded px-1.5 py-0.5 text-[10px] font-medium uppercase tracking-wide',
                    row.badge.className
                  )}
                >
                  {row.badge.label}
                </span>
              )}
              <FeedbackMark verdict={row.feedback} />
            </div>

            {/* Plain React children: this is LLM output and may echo
                third-party text (an event title, a mail subject). */}
            {row.content && (
              <p className="line-clamp-3 text-sm text-foreground/90">{row.content}</p>
            )}

            {row.chips.length > 0 && (
              <div className="flex flex-wrap gap-1">
                {row.chips.map(chip => (
                  <span
                    key={chip.key}
                    className="rounded border border-border/40 px-1.5 py-0.5 text-[10px] text-muted-foreground"
                  >
                    {chip.label}
                  </span>
                ))}
              </div>
            )}
          </li>
        ))}
      </ul>
      <p className="text-xs tabular-nums text-muted-foreground">{labels.count}</p>
    </div>
  );
}

/** The verdict already recorded — or the fact that none was. */
function FeedbackMark({ verdict }: { verdict: string | null }) {
  const { t } = useTranslation();
  if (verdict === 'thumbs_up') {
    return (
      <span className="flex items-center gap-1 text-xs text-green-600 dark:text-green-400">
        <ThumbsUp className="h-3 w-3" aria-hidden="true" />
        {t('heartbeat.history.feedback_thumbs_up')}
      </span>
    );
  }
  if (verdict === 'thumbs_down') {
    return (
      <span className="flex items-center gap-1 text-xs text-orange-600 dark:text-orange-400">
        <ThumbsDown className="h-3 w-3" aria-hidden="true" />
        {t('heartbeat.history.feedback_thumbs_down')}
      </span>
    );
  }
  return (
    <span className="flex items-center gap-1 text-xs text-muted-foreground">
      <AlertCircle className="h-3 w-3" aria-hidden="true" />
      {t('heartbeat.history.feedback_none')}
    </span>
  );
}
