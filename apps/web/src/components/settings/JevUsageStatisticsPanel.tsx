'use client';

import { Activity } from '@/lib/icons';
import { SeriesChart } from '@/components/effects/SeriesChart';
import { Disclosure } from '@/components/ui/disclosure';
import { InfoBox } from '@/components/ui/info-box';
import { useTranslation } from '@/i18n/client';
import type { Language } from '@/i18n/settings';
import { formatEuro, formatNumber } from '@/lib/format';
import type { JevAgreementRow, JevUsageStatistics } from '@/types/jev';

const PREFIX = 'settings.admin.jev.statistics';
/** The observer's three answers, in the order the question lists them. */
const VERDICTS = ['useful', 'empty', 'uncertain'] as const;

function AgreementTable({ lng, rows }: { lng: Language; rows: JevAgreementRow[] }) {
  const { t } = useTranslation(lng, 'translation');
  if (rows.length === 0) {
    return <p className="text-sm text-muted-foreground">{t(`${PREFIX}.noObservation`)}</p>;
  }
  const count = (verdict: string, proposed: boolean) =>
    rows
      .filter(row => row.verdict === verdict && row.proposed === proposed)
      .reduce((sum, row) => sum + row.count, 0);
  const verdicts = [
    ...VERDICTS,
    ...new Set(rows.map(row => row.verdict).filter(v => !VERDICTS.some(known => known === v))),
  ];
  const label = (verdict: string) =>
    VERDICTS.some(known => known === verdict) ? t(`${PREFIX}.verdicts.${verdict}`) : verdict;
  return (
    <table className="w-full table-fixed text-sm">
      <caption className="pb-2 text-left text-sm font-medium">
        {t(`${PREFIX}.agreementTitle`)}
        <span className="block text-xs font-normal text-muted-foreground">
          {t(`${PREFIX}.agreementHelp`)}
        </span>
      </caption>
      <thead>
        <tr className="border-b border-border text-xs text-muted-foreground">
          <th scope="col" className="py-1 text-left font-medium">
            {t(`${PREFIX}.verdictHeader`)}
          </th>
          <th scope="col" className="break-words py-1 text-right font-medium">
            {t(`${PREFIX}.proposed`)}
          </th>
          <th scope="col" className="break-words py-1 text-right font-medium">
            {t(`${PREFIX}.notProposed`)}
          </th>
        </tr>
      </thead>
      <tbody>
        {verdicts.map(verdict => (
          <tr key={verdict} className="border-b border-border last:border-0">
            <th scope="row" className="py-1 text-left font-normal">
              {label(verdict)}
            </th>
            <td className="py-1 text-right tabular-nums">
              {formatNumber(count(verdict, true), lng)}
            </td>
            <td className="py-1 text-right tabular-nums">
              {formatNumber(count(verdict, false), lng)}
            </td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

/**
 * One usage's window, folded: what it cost, how its operations ended and, for an
 * observer, how its verdicts compare with what the extractor itself proposed.
 */
export function JevUsageStatisticsPanel({
  lng,
  usageLabel,
  days,
  statistics,
  failed,
}: {
  lng: Language;
  usageLabel: string;
  /** The window the screen asked for, in whole UTC days. */
  days: number;
  /** Undefined while the first read is pending or after it failed. */
  statistics: JevUsageStatistics | undefined;
  /** The last read failed: said, while what an earlier read showed stays on screen. */
  failed: boolean;
}) {
  const { t } = useTranslation(lng, 'translation');
  const outcomes = Object.entries(statistics?.outcomes ?? {}).sort((a, b) => b[1] - a[1]);
  const operations = outcomes.reduce((sum, [, count]) => sum + count, 0);
  const latency = statistics?.latency_p50_ms;
  return (
    <Disclosure
      icon={Activity}
      title={t(`${PREFIX}.toggle`, { usage: usageLabel, count: days })}
      titleClassName="whitespace-normal break-words"
      badge={statistics ? formatNumber(statistics.calls, lng) : undefined}
      surface="nested"
    >
      {failed && (
        <InfoBox role="alert" variant="error">
          {t(`${PREFIX}.error`)}
        </InfoBox>
      )}
      {!failed && !statistics && (
        <p role="status" className="text-sm text-muted-foreground">
          {t('common.loading')}
        </p>
      )}
      {statistics && (
        <div className="space-y-3">
          <dl className="grid grid-cols-3 gap-2 text-center">
            <div className="rounded-md border border-border p-2">
              <dt className="text-xs text-muted-foreground">{t(`${PREFIX}.calls`)}</dt>
              <dd className="text-sm font-medium tabular-nums">
                {formatNumber(statistics.calls, lng)}
              </dd>
            </div>
            <div className="rounded-md border border-border p-2">
              <dt className="text-xs text-muted-foreground">{t(`${PREFIX}.cost`)}</dt>
              <dd className="text-sm font-medium tabular-nums">
                {formatEuro(statistics.cost_eur, 4, lng)}
              </dd>
            </div>
            <div className="rounded-md border border-border p-2">
              <dt className="text-xs text-muted-foreground">{t(`${PREFIX}.latency`)}</dt>
              <dd className="text-sm font-medium tabular-nums">
                {latency === null || latency === undefined
                  ? t(`${PREFIX}.noValue`)
                  : t(`${PREFIX}.latencyValue`, { value: formatNumber(latency, lng) })}
              </dd>
            </div>
          </dl>
          {operations === 0 ? (
            <p className="text-sm text-muted-foreground">{t(`${PREFIX}.noDecision`)}</p>
          ) : (
            <SeriesChart
              title={t(`${PREFIX}.outcomesTitle`)}
              description={t(`${PREFIX}.outcomesHelp`)}
              series={{
                slices: outcomes.map(([label, count]) => ({ label, count, secondary: 0 })),
                total: operations,
                kind: 'count',
              }}
              emptyLabel={t(`${PREFIX}.noDecision`)}
              countLabel={t(`${PREFIX}.operations`)}
            />
          )}
          {statistics.agreement !== null && (
            <AgreementTable lng={lng} rows={statistics.agreement} />
          )}
        </div>
      )}
    </Disclosure>
  );
}
