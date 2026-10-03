'use client';

import type { ReactNode } from 'react';
import { AlertCircle, ThumbsDown, ThumbsUp } from 'lucide-react';
import { useTranslation } from 'react-i18next';

import { Badge } from '@/components/ui/badge';
import { LoadingSpinner } from '@/components/ui/loading-spinner';
import { THEME_CHIP_TONE } from '@/lib/domain-tone';
import type { BadgeTone } from '@/lib/status-tone';
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
  /**
   * Emphasised marker (a priority, a state) — at most one.
   *
   * Carries a TONE, not classes: `Badge` renders it, so the marker inherits
   * the design-system contrast guard instead of hand-written Tailwind that
   * nothing checks. Density is what separates the levels — a solid fill reads
   * as more urgent than a tint even when the two hues are close.
   */
  badge?: { label: string; tone: BadgeTone; icon?: ReactNode } | null;
  /**
   * The chips: the sources used, the interest's provider, the person a
   * message was relayed with. `tone` is the chip's classes from
   * `lib/domain-tone` (a domain's colour); absent, the theme's primary — an
   * active fact is never drawn in the inactive grey.
   */
  chips: { key: string; label: string; tone?: string }[];
  /**
   * `thumbs_up` | `thumbs_down` | anything else, or null when never rated.
   * `undefined` for a row nobody can rate (a relayed message): no mark at all.
   */
  feedback?: string | null;
  /** Said instead of the content when it was not kept; absent, nothing is drawn. */
  contentFallback?: string;
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

  const formatDate = historyDateFormatter(locale);

  return (
    <div className="space-y-2">
      <ul className="space-y-2" role="list" aria-busy={loading || undefined}>
        {rows.map(row => (
          <NotificationHistoryItem key={row.id} row={row} formatDate={formatDate} />
        ))}
      </ul>
      <p className="text-xs tabular-nums text-muted-foreground">{labels.count}</p>
    </div>
  );
}

/**
 * The instant formatter of a history, built ONCE per render rather than once
 * per row: `Intl.DateTimeFormat` is expensive to construct and identical for
 * every line of the list.
 */
export function historyDateFormatter(locale: string): (iso: string) => string {
  let formatter: Intl.DateTimeFormat | null = null;
  try {
    formatter = new Intl.DateTimeFormat(locale, { dateStyle: 'medium', timeStyle: 'short' });
  } catch {
    // An unusable locale must not blank the history — the raw instant is
    // worse-looking and still true.
    formatter = null;
  }
  return (iso: string) => {
    if (!formatter) return iso;
    try {
      return formatter.format(new Date(iso));
    } catch {
      return iso;
    }
  };
}

/**
 * One line of a history — the date, the marker, the verdict, the words, the
 * chips. Exported so every list of the notification hub draws its lines the
 * same way (owner, 2026-10-03: the relayed messages had a layout of their own).
 */
export function NotificationHistoryItem({
  row,
  formatDate,
}: {
  row: NotificationHistoryRow;
  formatDate: (iso: string) => string;
}) {
  return (
    <li className="space-y-1.5 rounded-lg border border-border/40 bg-card/40 px-3 py-2">
      <div className="flex flex-wrap items-center gap-2">
        <time dateTime={row.createdAt} className="text-xs tabular-nums text-muted-foreground">
          {formatDate(row.createdAt)}
        </time>
        {row.badge && (
          <Badge
            variant={row.badge.tone}
            size="sm"
            icon={row.badge.icon}
            className="uppercase tracking-wide"
          >
            {row.badge.label}
          </Badge>
        )}
        {row.feedback !== undefined && <FeedbackMark verdict={row.feedback} />}
      </div>

      {/* Plain React children: this is LLM output, or words a person wrote,
          and may echo third-party text (an event title, a mail subject). */}
      {row.content ? (
        <p className="line-clamp-3 whitespace-pre-line text-sm text-foreground/90">{row.content}</p>
      ) : (
        row.contentFallback && (
          // Full `muted-foreground`, never a diluted /80: at this size the
          // faded pair measures under the 4.5:1 AA floor.
          <p className="text-xs italic text-muted-foreground">{row.contentFallback}</p>
        )
      )}

      {row.chips.length > 0 && (
        <div className="flex flex-wrap gap-1">
          {row.chips.map(chip => (
            <span
              key={chip.key}
              className={cn(
                'rounded border px-1.5 py-0.5 text-px-10 font-medium',
                chip.tone ?? THEME_CHIP_TONE
              )}
            >
              {chip.label}
            </span>
          ))}
        </div>
      )}
    </li>
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
