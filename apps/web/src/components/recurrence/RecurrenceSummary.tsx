'use client';

/**
 * What a recurrence will do, told to the reader before they save it.
 *
 * Three claims, and each one names its source:
 *
 * - **The sentence is the SERVER's** (`schedule_display`). Composing a second
 *   one here would be a second authority on the same fact, and the two would
 *   drift — so when the server has not composed one yet (a recurrence still
 *   being edited), this block simply does not render.
 * - **The moments are computed locally**, because the reader must see what a
 *   step produces while they are still choosing it and no round trip can
 *   answer between two keystrokes. That is arithmetic on wall clocks, with no
 *   timezone in it, so it cannot disagree with the server about WHICH moments
 *   a day holds.
 * - **The per-day figure is an UPPER BOUND.** A clock change makes the real
 *   count differ on one day a year (24 declared, 23 served in spring), so the
 *   wording says "up to N", never an exact number.
 *
 * The next dates are the server's instants, rendered in the RECURRENCE's own
 * zone — a routine evaluated in Paris fires at 08:00 Paris whether the reader
 * is in Paris or Tokyo.
 */

import { CalendarClock } from 'lucide-react';
import { useMemo } from 'react';
import { useTranslation } from 'react-i18next';

import type { RecurrenceSpec } from '@/types/recurrence';
import { renderOccurrences } from '@/lib/occurrences';
import { clockLabel, materialisedTimes, runsPerDay } from '@/lib/recurrence';

export interface RecurrenceSummaryProps {
  /** The recurrence being described. */
  spec: RecurrenceSpec;
  /** IANA zone the recurrence is evaluated in. */
  timezone: string;
  /** BCP-47 locale for dates and ordering. */
  locale: string;
  /** The sentence the server composed; absent while the reader is still editing. */
  sentence?: string;
  /** The server's upcoming instants (UTC ISO). */
  occurrences?: readonly string[];
  /** The series has no future left — say so rather than showing an empty list. */
  finished?: boolean;
}

export function RecurrenceSummary({
  spec,
  timezone,
  locale,
  sentence,
  occurrences,
  finished,
}: RecurrenceSummaryProps) {
  const { t } = useTranslation();

  const times = useMemo(() => materialisedTimes(spec.times).map(clockLabel), [spec.times]);
  const perDay = useMemo(() => runsPerDay(spec.times), [spec.times]);

  // `renderOccurrences` drops a NaN date, but `new Date(null)` is the EPOCH
  // and passes that filter — a finished series announced "01/01/1970". Only
  // non-empty strings reach it.
  const rendered = useMemo(() => {
    const usable = (occurrences ?? []).filter(
      (iso): iso is string => typeof iso === 'string' && iso.length > 0
    );
    return renderOccurrences(usable, timezone, locale);
  }, [occurrences, timezone, locale]);

  return (
    <div className="space-y-1.5 rounded-lg border border-border/40 bg-muted/30 p-3 text-xs">
      {sentence && (
        <p className="flex items-center gap-1.5 font-medium text-foreground" data-testid="recurrence-sentence">
          <CalendarClock className="h-3.5 w-3.5 shrink-0 text-primary" aria-hidden="true" />
          {sentence}
        </p>
      )}

      {times.length > 0 && (
        <p className="tabular-nums text-muted-foreground" data-testid="recurrence-times">
          {times.join(' · ')}
        </p>
      )}

      {perDay > 0 && (
        <p className="text-muted-foreground" data-testid="recurrence-per-day">
          {t('recurrence.summary_per_day', { count: perDay })}
        </p>
      )}

      {finished && <p className="text-muted-foreground">{t('recurrence.summary_finished')}</p>}

      {!finished && rendered.length > 0 && (
        <div>
          <span className="text-muted-foreground">{t('recurrence.summary_next')}</span>
          <ul className="mt-0.5 space-y-0.5" role="list" data-testid="recurrence-occurrences">
            {rendered.map(run => (
              <li key={run.iso} className="tabular-nums text-muted-foreground">
                <time dateTime={run.iso}>{run.label}</time>
                {run.zone && <span className="ml-1">{run.zone}</span>}
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}
