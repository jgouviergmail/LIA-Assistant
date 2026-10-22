'use client';

/**
 * How long ago AND when, in one phrase — « il y a 3 j le mardi 5 août 2026,
 * 14:05 », the amount and the moment in bold (owner request 2026-10-21).
 *
 * The relative part alone says how far; it never says when, which is what a
 * reader needs before calling back or replying. An upcoming meeting reads
 * « dans 3 j le … »: the relative helper used to clamp the future to « just
 * now ». A slot (start and end) keeps both clocks; an all-day entry keeps no
 * clock at all, as `dateTimeRangeLabel` decides.
 *
 * The phrase carries its own style: it titles every dated row of a
 * relationship — the mail rows' line, extended to every section but the
 * contact card (owner request 2026-10-21) — so a caller adds layout, never a
 * second look. Full `text-muted-foreground`, never a diluted `/80`: at 11px
 * the faded pair measures 3.51:1, under the 4.5:1 AA floor (axe, production
 * bundle).
 */

import { Trans, useTranslation } from 'react-i18next';

import { dateTimeRangeLabel, relativeTense } from '@/lib/briefing-utils';
import { cn } from '@/lib/utils';

const AMOUNT_KEYS = {
  minutes: 'relations.when.minutes',
  hours: 'relations.when.hours',
  days: 'relations.when.days',
} as const;

export function RelationWhen({
  start,
  end = null,
  className,
}: {
  /** ISO 8601 UTC instant (or a slot's start). */
  start: string | null;
  /** ISO 8601 UTC end of a slot, when the source has one. */
  end?: string | null;
  /** Layout only — the look is the phrase's own. */
  className?: string;
}) {
  const { t, i18n } = useTranslation();
  const relative = start ? relativeTense(start) : null;
  const when = dateTimeRangeLabel(i18n.language, start, end, { weekday: true });
  if (!relative || !when) return null;
  const { bucket } = relative;
  const ago = bucket.kind === 'just_now' ? '' : t(AMOUNT_KEYS[bucket.kind], { n: bucket.count });
  return (
    <span className={cn('text-px-11 tabular-nums text-muted-foreground', className)}>
      <Trans
        i18nKey={`relations.when.${relative.tense}`}
        values={{ ago, when }}
        components={{ strong: <strong className="font-semibold" /> }}
      >
        {/* The default value only: the six locales all carry the key. */}
        <strong className="font-semibold">{ago}</strong>{' '}
        <strong className="font-semibold">{when}</strong>
      </Trans>
    </span>
  );
}
