'use client';

/**
 * Why LIA thinks this subject matters to you.
 *
 * The panel showed a percentage badge and a date. Someone deciding whether to
 * BLOCK a subject could see that LIA rated it 46 % and nothing about why — not
 * how many signals, not how old they were, not which conversation started it.
 *
 * **This explains; it does not score.** No rank, no level, no comparison with
 * anyone: a Beta mean IS an uncertainty estimate, and "two signals, so this is
 * still a guess" serves a decision in a way a leaderboard never could. The
 * coefficients are published beside the number so the reader can rebuild it
 * rather than trust it (ADR-184) — the same number the ranking applies, which
 * has not always been true of the one on screen.
 *
 * Blocking keeps its own explanation, untouched: it is the strongest action
 * the panel offers and it already says what it does.
 */

import { Scale } from 'lucide-react';
import { useTranslation } from 'react-i18next';

import { LoadingSpinner } from '@/components/ui/loading-spinner';
import { ProvenanceDisclosure } from '@/components/provenance/ProvenanceDisclosure';
import { SettingsDisclosure } from '@/components/settings/SettingsDisclosure';
import { useApiQuery } from '@/hooks/useApiQuery';
import { formatInstant } from '@/lib/format-instant';
import { useState } from 'react';

export interface InterestExplanationPayload {
  positive_signals: number;
  negative_signals: number;
  prior_alpha: number;
  prior_beta: number;
  base_weight: number;
  decay_rate_per_day: number;
  decay_floor: number;
  days_since_last_mention: number;
  effective_weight: number;
  last_mentioned_at: string;
  last_notified_at: string | null;
  status: string;
  dormant_since: string | null;
}

export interface InterestExplanationProps {
  interestId: string;
  /** BCP-47 locale for dates. */
  locale: string;
}

/** One labelled fact of the explanation. */
function Fact({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex flex-wrap items-baseline gap-1.5">
      <dt className="text-[11px] text-muted-foreground">{label}</dt>
      <dd className="text-xs tabular-nums text-foreground/90">{value}</dd>
    </div>
  );
}

export function InterestExplanation({ interestId, locale }: InterestExplanationProps) {
  const { t } = useTranslation();
  const [open, setOpen] = useState(false);

  const { data, loading, error } = useApiQuery<InterestExplanationPayload>(
    `/interests/${interestId}/explanation`,
    { componentName: 'InterestExplanation', enabled: open }
  );

  // Derived from the ABSENCE of data, never from `error`.
  const firstLoad = data === undefined && loading;
  const percent = (value: number) => `${Math.round(value * 100)} %`;

  return (
    <SettingsDisclosure
      icon={Scale}
      title={t('interests.explanation.title')}
      onOpenChange={setOpen}
      // A phone does not get this block: it is dense by nature — a list of
      // dated signals, or the six coefficients behind a weight — and it pushed
      // the thing the reader came for off a small screen. Hidden in CSS rather
      // than unmounted: the disclosure renders its children only when open, so
      // a closed one already costs no request, and a JS-driven variant would
      // make the server and the first client paint disagree.
      className="mt-2 hidden sm:block"
    >
      {firstLoad ? (
        <div className="flex justify-center py-4">
          <LoadingSpinner className="h-4 w-4" />
        </div>
      ) : error && !data ? (
        // Checked BEFORE emptiness: an unexplained interest and an unreadable
        // explanation are different things to say.
        <p role="alert" className="text-xs text-destructive">
          {t('interests.explanation.error')}
        </p>
      ) : data ? (
        <div className="space-y-2">
          {/* The sentence first: a reader wants the reason, not the arithmetic.
              The uncertainty is stated in words — "few signals" — because that
              is what decides whether to keep or block a subject. */}
          <p className="text-xs text-foreground/90">
            {t('interests.explanation.summary', {
              positives: data.positive_signals,
              negatives: data.negative_signals,
              days: data.days_since_last_mention,
              weight: percent(data.effective_weight),
            })}
          </p>
          {data.positive_signals + data.negative_signals <= 2 && (
            <p className="text-xs italic text-muted-foreground">
              {t('interests.explanation.low_confidence')}
            </p>
          )}

          <dl className="grid grid-cols-1 gap-1 sm:grid-cols-2">
            <Fact
              label={t('interests.explanation.signals')}
              value={t('interests.explanation.signals_value', {
                positives: data.positive_signals,
                negatives: data.negative_signals,
              })}
            />
            <Fact
              label={t('interests.explanation.last_mention')}
              value={formatInstant(data.last_mentioned_at, locale)}
            />
            <Fact
              label={t('interests.explanation.last_notification')}
              value={
                data.last_notified_at
                  ? formatInstant(data.last_notified_at, locale)
                  : t('interests.explanation.never_notified')
              }
            />
            <Fact
              label={t('interests.explanation.base_weight')}
              value={percent(data.base_weight)}
            />
          </dl>

          {/* The coefficients, so the number above is checkable rather than
              merely asserted. An enforced constant nobody can see is a trap. */}
          <p className="text-[11px] text-muted-foreground">
            {t('interests.explanation.formula', {
              alpha: data.prior_alpha,
              beta: data.prior_beta,
              rate: (data.decay_rate_per_day * 100).toFixed(1),
              floor: percent(data.decay_floor),
            })}
          </p>
        </div>
      ) : null}

      {/* Where it came from — the same block journals and memories use, so one
          question has one answer everywhere in the product. */}
      <ProvenanceDisclosure endpoint={`/interests/${interestId}/provenance`} locale={locale} />
    </SettingsDisclosure>
  );
}
