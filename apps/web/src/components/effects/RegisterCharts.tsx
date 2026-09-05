'use client';

/**
 * RegisterCharts — the five records, seen at a glance (ADR-263).
 *
 * The registers answer « what exactly happened »; this answers « what has been
 * happening ». Both matter and neither replaces the other, which is why this is
 * a third view beside the two journals rather than something bolted onto them.
 *
 * One component for both audiences: a reader looking at their own records and
 * an operator looking at one, several or every account see the SAME cards, from
 * the same computation. Two renderings would be two places for a figure to be
 * right on one screen and wrong on the other.
 *
 * The timeline stays chronological while every other card is largest-first —
 * a chronology sorted by size is not a chronology.
 */

import { Activity } from 'lucide-react';
import { useMemo } from 'react';
import {
  Area,
  AreaChart,
  CartesianGrid,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts';
import { useTranslation } from 'react-i18next';

import { SeriesChart } from '@/components/effects/SeriesChart';
import { Card, CardContent } from '@/components/ui/card';
import { Skeleton } from '@/components/ui/skeleton';
import { getIntlLocale, type Language } from '@/i18n/settings';
import {
  useRegisterStatistics,
  type UseRegisterStatisticsOptions,
} from '@/hooks/useRegisterStatistics';

export type RegisterChartsProps = UseRegisterStatisticsOptions;

const TOOLTIP_CONTENT_STYLE: React.CSSProperties = {
  backgroundColor: 'var(--color-popover)',
  borderColor: 'var(--color-border)',
  borderRadius: '6px',
  color: 'var(--color-popover-foreground)',
};

export function RegisterCharts(options: RegisterChartsProps) {
  const { t, i18n } = useTranslation();
  const { statistics, loading, error } = useRegisterStatistics(options);
  const locale = getIntlLocale(i18n.language as Language);

  const dayFormat = useMemo(
    () => new Intl.DateTimeFormat(locale, { day: 'numeric', month: 'short' }),
    [locale]
  );

  const timeline = useMemo(
    () =>
      (statistics?.activity_by_day.slices ?? []).map(slice => ({
        day: dayFormat.format(new Date(`${slice.label}T00:00:00Z`)),
        count: slice.count,
      })),
    [statistics, dayFormat]
  );

  // A skeleton of the real geometry: the cards sit below a tab, and appearing
  // late would push the page under the reader's pointer.
  if (loading && !statistics) {
    return (
      <div className="grid gap-4 lg:grid-cols-2">
        {[0, 1, 2, 3].map(index => (
          <Card key={index}>
            <CardContent className="p-4">
              <Skeleton className="h-40 w-full" label={t('registers.charts.loading')} />
            </CardContent>
          </Card>
        ))}
      </div>
    );
  }

  if (error) {
    return (
      <p className="py-8 text-center text-sm text-destructive">{t('registers.charts.error')}</p>
    );
  }

  const empty = t('registers.charts.empty');
  const label = (key: string) => (raw: string) =>
    t(`registers.charts.${key}.${raw}`, { defaultValue: raw });

  return (
    <div className="space-y-4">
      {/* The chronology first: it says WHEN, and every card below says what. */}
      <Card className="min-w-0">
        <CardContent className="space-y-3 p-4">
          <h3 className="flex items-center gap-2 text-sm font-medium">
            <Activity className="h-4 w-4 text-primary" aria-hidden="true" />
            {t('registers.charts.activity.title')}
          </h3>
          <p className="text-xs text-muted-foreground">
            {t('registers.charts.activity.description')}
          </p>
          {timeline.length === 0 ? (
            <p className="py-6 text-center text-sm text-muted-foreground">{empty}</p>
          ) : (
            <div style={{ width: '100%', height: 200 }}>
              <ResponsiveContainer width="100%" height="100%">
                <AreaChart data={timeline} margin={{ left: 4, right: 8, top: 8 }}>
                  <CartesianGrid strokeDasharray="3 3" stroke="var(--color-border)" />
                  <XAxis
                    dataKey="day"
                    tick={{ fontSize: 11 }}
                    stroke="var(--color-muted-foreground)"
                  />
                  <YAxis
                    allowDecimals={false}
                    tick={{ fontSize: 11 }}
                    stroke="var(--color-muted-foreground)"
                  />
                  <Tooltip contentStyle={TOOLTIP_CONTENT_STYLE} />
                  <Area
                    type="monotone"
                    dataKey="count"
                    name={t('registers.charts.activity.legend')}
                    stroke="var(--color-primary)"
                    fill="var(--color-primary)"
                    fillOpacity={0.2}
                  />
                </AreaChart>
              </ResponsiveContainer>
            </div>
          )}
        </CardContent>
      </Card>

      {/* One column on a phone, two from `lg` up: twelve horizontal bars need
          the width, and side by side they would be unreadable on a handset. */}
      <div className="grid gap-4 lg:grid-cols-2">
        <SeriesChart
          title={t('registers.charts.turns_outcome.title')}
          description={t('registers.charts.turns_outcome.description')}
          series={statistics?.turns_by_outcome}
          emptyLabel={empty}
          countLabel={t('registers.charts.legend.turns')}
          renderLabel={label('outcome')}
          tone="primary"
        />
        <SeriesChart
          title={t('registers.charts.turns_mode.title')}
          description={t('registers.charts.turns_mode.description')}
          series={statistics?.turns_by_mode}
          emptyLabel={empty}
          countLabel={t('registers.charts.legend.turns')}
          tone="primary"
        />
        <SeriesChart
          title={t('registers.charts.actions_status.title')}
          description={t('registers.charts.actions_status.description')}
          series={statistics?.actions_by_status}
          emptyLabel={empty}
          countLabel={t('registers.charts.legend.actions')}
          renderLabel={label('status')}
          tone="success"
        />
        <SeriesChart
          title={t('registers.charts.consultations_domain.title')}
          description={t('registers.charts.consultations_domain.description')}
          series={statistics?.consultations_by_domain}
          emptyLabel={empty}
          countLabel={t('registers.charts.legend.consultations')}
          renderLabel={label('domain')}
          tone="success"
        />
        <SeriesChart
          title={t('registers.charts.latency.title')}
          description={t('registers.charts.latency.description')}
          series={statistics?.consultation_latency_by_tool}
          emptyLabel={empty}
          countLabel={t('registers.charts.legend.latency')}
          unit="ms"
          tone="warning"
        />
        <SeriesChart
          title={t('registers.charts.calls_model.title')}
          description={t('registers.charts.calls_model.description')}
          series={statistics?.calls_by_model}
          emptyLabel={empty}
          countLabel={t('registers.charts.legend.calls')}
          tone="primary"
        />
        <SeriesChart
          title={t('registers.charts.calls_node.title')}
          description={t('registers.charts.calls_node.description')}
          series={statistics?.calls_by_node}
          emptyLabel={empty}
          countLabel={t('registers.charts.legend.calls')}
          tone="primary"
        />
        <SeriesChart
          title={t('registers.charts.tokens_model.title')}
          description={t('registers.charts.tokens_model.description')}
          series={statistics?.tokens_by_model}
          emptyLabel={empty}
          countLabel={t('registers.charts.legend.prompt_tokens')}
          secondaryLabel={t('registers.charts.legend.completion_tokens')}
          tone="primary"
        />
        <SeriesChart
          title={t('registers.charts.integrity.title')}
          description={t('registers.charts.integrity.description')}
          series={statistics?.integrity_by_kind}
          // Empty is the GOOD news here, and it deserves a sentence rather
          // than the neutral one every other card shows.
          emptyLabel={t('registers.charts.integrity.empty')}
          countLabel={t('registers.charts.legend.gaps')}
          renderLabel={label('integrity_kind')}
          tone="destructive"
        />
      </div>
    </div>
  );
}
