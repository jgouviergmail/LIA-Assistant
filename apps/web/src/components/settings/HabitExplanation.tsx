'use client';

/**
 * Why LIA claims this habit — the interests-explanation doctrine applied to
 * habits (ADR-214): inputs and enforced thresholds, never a score.
 *
 * For a recurring habit the block shows the ledger's REAL occurrence dates —
 * the exact basis of the lock. The ledger keeps no message ids on purpose,
 * so no conversation links are shown: fabricated references would be false
 * provenance (stated program deviation).
 */

import { Scale } from 'lucide-react';
import { useState } from 'react';

import { LoadingSpinner } from '@/components/ui/loading-spinner';
import { SettingsDisclosure } from '@/components/settings/SettingsDisclosure';
import { useApiQuery } from '@/hooks/useApiQuery';
import { useTranslation } from '@/i18n/client';
import type { Language } from '@/i18n/settings';

const MAX_DATES_SHOWN = 8;

export interface HabitExplanationPayload {
  kind: string;
  key: string;
  payload: Record<string, unknown>;
  positive_signals: number;
  negative_signals: number;
  status: string;
  last_observed_at: string;
  thresholds: Record<string, number>;
  observed_days: string[];
}

export function HabitExplanation({ lng, habitId }: { lng: Language; habitId: string }) {
  const { t, i18n } = useTranslation(lng);
  const [open, setOpen] = useState(false);

  const { data, loading, error } = useApiQuery<HabitExplanationPayload>(
    `/habits/${habitId}/explanation`,
    { componentName: 'HabitExplanation', enabled: open }
  );

  // Derived from the ABSENCE of data, never from `error` (refetch resets it).
  const firstLoad = data === undefined && loading;
  // One formatter per render, never one per date (render-loop Intl trap).
  const dateFormat = new Intl.DateTimeFormat(i18n.language, { day: '2-digit', month: 'short' });
  const dateLabel = (iso: string) => dateFormat.format(new Date(`${iso}T00:00:00`));

  return (
    <SettingsDisclosure
      icon={Scale}
      title={t('settings.habits.explanation.title')}
      onOpenChange={setOpen}
      // Dense by nature — phones keep the row itself (interests precedent).
      className="mt-1 hidden sm:block"
    >
      {firstLoad ? (
        <div className="flex justify-center py-3">
          <LoadingSpinner className="h-4 w-4" />
        </div>
      ) : error && !data ? (
        <p role="alert" className="text-xs text-destructive">
          {t('settings.habits.explanation.error')}
        </p>
      ) : data ? (
        <div className="space-y-2">
          {data.observed_days.length > 0 && (
            <div className="space-y-1">
              <p className="text-[11px] text-muted-foreground">
                {t('settings.habits.explanation.observed_label')}
              </p>
              <p className="text-xs tabular-nums text-foreground/90">
                {data.observed_days.slice(0, MAX_DATES_SHOWN).map(dateLabel).join(' · ')}
                {data.observed_days.length > MAX_DATES_SHOWN &&
                  ` ${t('settings.habits.explanation.more_days', {
                    count: data.observed_days.length - MAX_DATES_SHOWN,
                  })}`}
              </p>
            </div>
          )}
          {/* The exact thresholds the detector applied (ADR-184): checkable,
              never merely asserted. */}
          <p className="text-[11px] text-muted-foreground">
            {t('settings.habits.explanation.thresholds_label')}{' '}
            <span className="tabular-nums">
              {Object.entries(data.thresholds)
                .map(([name, value]) => `${name}=${value}`)
                .join(' · ')}
            </span>
          </p>
        </div>
      ) : null}
    </SettingsDisclosure>
  );
}
