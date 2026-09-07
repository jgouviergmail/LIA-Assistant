'use client';

/**
 * RegisterRow — one row, one geometry, for every register reading.
 *
 * The action journal and the consultation journal grew two nearly identical
 * renderers, and they drifted: consultations showed the capability and the
 * duration, actions showed neither. A reader moving between the two tabs — and
 * now a third, « LIA's own initiative », which mounts both — saw the same kind
 * of event described in two different amounts of detail (owner report,
 * 2026-09-07).
 *
 * Two renderings are two places for the same figure to be right on one screen
 * and missing on the other, which is exactly the argument ADR-263 already made
 * for the charts. So there is one row, and homogeneity is structural rather
 * than watched: a field added here appears in all three readings at once.
 *
 * What differs legitimately between the registers stays a PROP — the headline
 * (a label for an action, a domain for a consultation) and the badges (an
 * outcome vocabulary of five against one of two). What is common is fixed
 * here: the glyph and its tone, the time, the capability, the duration and the
 * authorship, in that order.
 */

import type { LucideIcon } from 'lucide-react';
import type { ReactNode } from 'react';
import { useTranslation } from 'react-i18next';

import { cn } from '@/lib/utils';
import type { EffectSource } from '@/types/effects';

export interface RegisterRowProps {
  /** Decorative glyph; the badges carry the meaning. */
  icon: LucideIcon;
  /** Red tone for a failure, theme tone otherwise. */
  failed: boolean;
  /** What happened, in the reader's language. */
  headline: string;
  /** Formatted time of day. */
  when: string;
  /** Machine-readable instant for `<time dateTime>`. */
  dateTime: string;
  /** Register-specific badges, rendered beside the headline. */
  headlineBadges?: ReactNode;
  /** Register-specific badges, rendered on the detail line. */
  detailBadges?: ReactNode;
  /** The capability, verbatim — a bounded name, never free text. */
  capability: string;
  /**
   * Wall-clock duration in milliseconds, or `null` when it is not knowable —
   * an effect still in flight has no end yet, and inventing a zero would read
   * as "instant" rather than "not finished".
   */
  durationMs: number | null;
  /** Who set the turn in motion. */
  source: EffectSource;
}

export function RegisterRow({
  icon: Icon,
  failed,
  headline,
  when,
  dateTime,
  headlineBadges,
  detailBadges,
  capability,
  durationMs,
  source,
}: RegisterRowProps) {
  const { t } = useTranslation();

  return (
    <li className="flex items-start gap-3 rounded-xl border bg-card px-4 py-3">
      <span
        className={cn(
          'mt-0.5 flex h-8 w-8 shrink-0 items-center justify-center rounded-lg',
          failed ? 'bg-destructive/10 text-destructive' : 'bg-primary/10 text-primary'
        )}
      >
        <Icon className="h-4 w-4" aria-hidden="true" />
      </span>
      <span className="min-w-0 flex-1">
        <span className="flex flex-wrap items-baseline gap-x-2">
          <span className="min-w-0 break-words text-sm font-semibold text-foreground">
            {headline}
          </span>
          <time dateTime={dateTime} className="text-xs text-muted-foreground">
            {when}
          </time>
          {headlineBadges}
        </span>
        <span className="mt-1 flex flex-wrap items-center gap-1.5">
          {detailBadges}
          <span className="min-w-0 break-words font-mono text-xs text-muted-foreground">
            {capability}
          </span>
          {durationMs !== null && (
            <span className="text-xs text-muted-foreground">
              {t('registers.row.duration', { ms: durationMs })}
            </span>
          )}
          <span className="text-xs text-muted-foreground">
            {t(`effects.journal.source.${source}`)}
          </span>
        </span>
      </span>
    </li>
  );
}
