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
   * A relayed message names its peer beside the direction, never twice. A
   * node, so the caller can set the name in bold and the words around it
   * plain (owner request 2026-10-21).
   */
  attribution?: ReactNode;
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

/**
 * How the rows are set apart — never how one reads: the hub's timeline draws a
 * rule between them, the settings frame each in a panel of its own on the card
 * ground (owner request 2026-10-21: one sub-panel per row, no rule between).
 */
export type NotificationHistoryPresentation = 'panels' | 'timeline';

/** The frame of one row, per presentation. */
const ROW_FRAME: Record<NotificationHistoryPresentation, string> = {
  timeline: 'min-w-0 space-y-3 border-b border-border py-4 last:border-b-0',
  panels: 'min-w-0 space-y-3 rounded-lg border bg-card p-3',
};

export interface NotificationHistoryListProps {
  presentation?: NotificationHistoryPresentation;
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
  presentation = 'panels',
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
    <div className="min-w-0 space-y-2">
      <ul
        className={presentation === 'timeline' ? 'min-w-0' : 'space-y-2'}
        role="list"
        aria-busy={loading || undefined}
      >
        {rows.map(row => (
          <NotificationHistoryItem
            key={row.id}
            row={row}
            formatDate={formatDate}
            presentation={presentation}
            // The date titles the row; the marker leads the line under it.
            metadataPosition="header"
          />
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
  presentation = 'panels',
  metadataPosition = 'footer',
  badgePlacement = 'meta',
}: {
  row: NotificationHistoryRow;
  formatDate: (iso: string) => string;
  presentation?: NotificationHistoryPresentation;
  metadataPosition?: 'header' | 'footer';
  /**
   * Where the hub's timeline draws the marker: leading the line under the
   * date (`meta`), or leading the message itself (`content`) — an SMS names
   * its sender where its words begin (owner request 2026-10-21). A row with
   * no message keeps it under the date.
   */
  badgePlacement?: 'meta' | 'content';
}) {
  const headerMetadata = metadataPosition === 'header';
  const slot = badgeSlot(row, headerMetadata, badgePlacement);
  const badge = row.badge ? <HistoryBadge badge={row.badge} inline={slot === 'content'} /> : null;

  return (
    <li className={ROW_FRAME[presentation]}>
      <HistoryHeading
        row={row}
        formatDate={formatDate}
        headerMetadata={headerMetadata}
        badge={slot === 'heading' ? badge : null}
      />

      {headerMetadata && <HistoryMeta row={row} badge={slot === 'meta' ? badge : null} />}

      <HistoryContent row={row} lead={slot === 'content' ? badge : null} />

      {!headerMetadata && <HistoryChips chips={row.chips} />}
    </li>
  );
}

/**
 * Where a row's marker is drawn: on the line under the date (its own, or the
 * metadata line it leads), or leading the message itself. A row asking for
 * `content` but holding no message keeps its marker under the date.
 */
function badgeSlot(
  row: NotificationHistoryRow,
  headerMetadata: boolean,
  placement: 'meta' | 'content'
): 'heading' | 'meta' | 'content' {
  if (placement === 'content' && row.content) return 'content';
  return headerMetadata ? 'meta' : 'heading';
}

/**
 * The line under the date when the metadata leads: the marker FIRST, then the
 * sources and the verdict (owner request 2026-10-21) — the date is the row's
 * title.
 */
function HistoryMeta({ row, badge }: { row: NotificationHistoryRow; badge: ReactNode }) {
  return (
    <div className="flex flex-wrap items-center gap-x-3 gap-y-1">
      {badge}
      <HistoryChips chips={row.chips} />
      {row.feedback !== undefined && <FeedbackMark verdict={row.feedback} />}
    </div>
  );
}

/**
 * The message — or the sentence saying it was not kept. Plain React children:
 * this is LLM output, or words a person wrote, and may echo third-party text
 * (an event title, a mail subject). `lead` opens the message (an SMS's sender).
 */
function HistoryContent({ row, lead }: { row: NotificationHistoryRow; lead: ReactNode }) {
  if (row.content) {
    return (
      <p className="whitespace-pre-line break-words text-sm leading-relaxed text-foreground/90">
        {lead}
        {row.content}
      </p>
    );
  }
  if (!row.contentFallback) return null;
  // Full `muted-foreground`, never a diluted /80: at this size the faded pair
  // measures under the 4.5:1 AA floor.
  return <p className="break-words text-xs italic text-muted-foreground">{row.contentFallback}</p>;
}

/**
 * The date and, unless the caller drew it elsewhere, the badge, the
 * attribution and the verdict. The date is the row's title: it takes a line of
 * its own, and everything else follows below it.
 */
function HistoryHeading({
  row,
  formatDate,
  headerMetadata,
  badge,
}: {
  row: NotificationHistoryRow;
  formatDate: (iso: string) => string;
  headerMetadata: boolean;
  /** The marker, when it belongs to this line — null when drawn elsewhere. */
  badge: ReactNode;
}) {
  return (
    <div className="flex flex-wrap items-center gap-2">
      <time
        dateTime={row.createdAt}
        className="w-full break-words text-xs font-bold tabular-nums text-muted-foreground"
      >
        {formatDate(row.createdAt)}
      </time>
      {badge}
      {row.attribution && <span className="min-w-0 break-words text-sm">{row.attribution}</span>}
      {!headerMetadata && row.feedback !== undefined && <FeedbackMark verdict={row.feedback} />}
    </div>
  );
}

/** The row's marker — a priority, a state, a subject, a sender. */
function HistoryBadge({
  badge,
  inline,
}: {
  badge: NonNullable<NotificationHistoryRow['badge']>;
  /** Leading the message's own text: no taller than its line, a gap after it. */
  inline: boolean;
}) {
  return (
    <Badge
      variant={badge.tone}
      size="sm"
      icon={badge.icon}
      className={cn(
        'h-auto min-w-0 max-w-full py-1 font-bold leading-relaxed',
        inline && 'mr-2 py-0 leading-normal'
      )}
    >
      <span className="min-w-0 break-words">{badge.label}</span>
    </Badge>
  );
}

/** One vocabulary of source labels, shared by header and footer metadata. */
function HistoryChips({ chips }: { chips: NotificationHistoryRow['chips'] }) {
  if (!chips.length) return null;
  return (
    <div className="flex min-w-0 max-w-full flex-wrap gap-x-3 gap-y-1">
      {chips.map(chip => (
        // The domain's colour, as a word: its tint and its edge are dropped.
        <span
          key={chip.key}
          className={cn(
            chip.tone ?? THEME_CHIP_TONE,
            'min-w-0 max-w-full break-words rounded-none border-0 bg-transparent px-0 py-0 text-xs font-bold leading-relaxed'
          )}
        >
          {chip.label}
        </span>
      ))}
    </div>
  );
}

/** The verdict already recorded — or the fact that none was. */
function FeedbackMark({ verdict }: { verdict: string | null }) {
  const { t } = useTranslation();
  if (verdict === 'thumbs_up') {
    return (
      <span className="flex items-center gap-1 text-xs font-bold text-success">
        <ThumbsUp className="h-3 w-3" aria-hidden="true" />
        {t('heartbeat.history.feedback_thumbs_up')}
      </span>
    );
  }
  if (verdict === 'thumbs_down') {
    return (
      <span className="flex items-center gap-1 text-xs font-bold text-destructive">
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
