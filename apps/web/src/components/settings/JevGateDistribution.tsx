'use client';

import { BarChart3 } from '@/lib/icons';
import { SeriesChart } from '@/components/effects/SeriesChart';
import { Disclosure } from '@/components/ui/disclosure';
import { useTranslation } from '@/i18n/client';
import { getIntlLocale, type Language } from '@/i18n/settings';
import { formatNumber } from '@/lib/format';
import { concludedShare, thresholdBands } from '@/lib/jev-statistics';
import type { JevGateStatistics } from '@/types/jev';

const PREFIX = 'settings.admin.jev.statistics';
/** Fits « 0,90–1,00 » at the chart's 11 px, so the bars keep the room on a phone. */
const BAND_AXIS_WIDTH = 72;

/**
 * What one gate's judgements of the window conclude at the threshold the slider shows.
 *
 * Read from the buckets alone (`lib/jev-statistics.ts`), so the share follows the slider
 * as it moves, before anything is saved. The bands stack, per tenth of score, what
 * concludes and what hands back to the existing processing.
 */
export function JevGateDistribution({
  lng,
  statistics,
  value,
}: {
  lng: Language;
  statistics: JevGateStatistics;
  /** The threshold being read: the slider's draft while it moves, else the stored one. */
  value: number;
}) {
  const { t } = useTranslation(lng, 'translation');
  const { concluded, total } = concludedShare(statistics.kind, statistics.buckets, value);
  if (total === 0) {
    return <p className="text-xs text-muted-foreground">{t(`${PREFIX}.noJudgement`)}</p>;
  }
  const share = new Intl.NumberFormat(getIntlLocale(lng), {
    style: 'percent',
    maximumFractionDigits: 1,
  }).format(concluded / total);
  const score = (bound: number) =>
    bound.toLocaleString(getIntlLocale(lng), {
      minimumFractionDigits: 2,
      maximumFractionDigits: 2,
    });
  const bands = thresholdBands(statistics.kind, statistics.buckets, value);
  const chartTitle = t(
    statistics.kind === 'margin' ? `${PREFIX}.chartMargin` : `${PREFIX}.chartConfidence`
  );
  return (
    <div className="space-y-2">
      <p className="text-xs text-muted-foreground">
        {t(`${PREFIX}.share`, { share, count: total, total: formatNumber(total, lng) })}
      </p>
      <Disclosure
        icon={BarChart3}
        title={t(`${PREFIX}.distribution`)}
        titleClassName="whitespace-normal break-words"
        badge={formatNumber(total, lng)}
        surface="nested"
      >
        <SeriesChart
          title={chartTitle}
          description={t(`${PREFIX}.chartHelp`)}
          series={{
            slices: bands.map(band => ({
              label: t(`${PREFIX}.band`, { from: score(band.from), to: score(band.to) }),
              count: band.concludes,
              secondary: band.handsBack,
            })),
            total,
            kind: 'stacked',
          }}
          emptyLabel={t(`${PREFIX}.noJudgement`)}
          countLabel={t(`${PREFIX}.concludes`)}
          secondaryLabel={t(`${PREFIX}.handsBack`)}
          categoryWidth={BAND_AXIS_WIDTH}
        />
      </Disclosure>
    </div>
  );
}
