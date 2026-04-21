/**
 * HealthMetricsCharts — recharts-based visualization for health metrics.
 *
 * Displays a heart-rate line chart (with period-average reference line)
 * and a daily-steps bar chart (with period-average reference line).
 *
 * Phase: evolution — Health Metrics (iPhone Shortcuts integration)
 * Created: 2026-04-20
 */

'use client';

import { useMemo } from 'react';
import {
  Bar,
  BarChart,
  CartesianGrid,
  Line,
  LineChart,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts';

import { useTranslation } from '@/i18n/client';
import type { Language } from '@/i18n/settings';
import type {
  HealthMetricsAggregateResponse,
  HealthMetricsPeriod,
} from '@/hooks/useHealthMetrics';

interface HealthMetricsChartsProps {
  lng: Language;
  aggregate: HealthMetricsAggregateResponse | undefined;
  period: HealthMetricsPeriod;
}

type ChartRow = {
  bucket: string;
  label: string;
  heart_rate_avg: number | null;
  steps_total: number | null;
};

function formatBucket(iso: string, period: HealthMetricsPeriod, lng: Language): string {
  const d = new Date(iso);
  const locale = lng || 'fr';
  if (period === 'hour') {
    return d.toLocaleTimeString(locale, { hour: '2-digit', minute: '2-digit' });
  }
  if (period === 'day') {
    return d.toLocaleDateString(locale, { weekday: 'short', day: '2-digit', month: 'short' });
  }
  if (period === 'week') {
    return d.toLocaleDateString(locale, { day: '2-digit', month: 'short' });
  }
  if (period === 'month') {
    return d.toLocaleDateString(locale, { month: 'short', year: 'numeric' });
  }
  return d.toLocaleDateString(locale, { year: 'numeric' });
}

export function HealthMetricsCharts({ lng, aggregate, period }: HealthMetricsChartsProps) {
  const { t } = useTranslation(lng, 'translation');

  const rows: ChartRow[] = useMemo(() => {
    if (!aggregate) return [];
    return aggregate.points.map(p => ({
      bucket: p.bucket,
      label: formatBucket(p.bucket, period, lng),
      heart_rate_avg: p.heart_rate_avg,
      steps_total: p.steps_total,
    }));
  }, [aggregate, period, lng]);

  const hasHrData = rows.some(r => r.heart_rate_avg !== null);
  const hasStepsData = rows.some(r => r.steps_total !== null);

  const hrAvg = aggregate?.averages.heart_rate_avg ?? null;
  const stepsAvg = aggregate?.averages.steps_per_day_avg ?? null;

  return (
    <div className="space-y-8">
      {/* Heart rate */}
      <div>
        <div className="flex items-baseline justify-between mb-3">
          <h4 className="text-sm font-semibold">
            {t('healthMetrics.charts.heartRate', 'Fréquence cardiaque (bpm)')}
          </h4>
          {hrAvg !== null && (
            <span className="text-xs text-muted-foreground">
              {t('healthMetrics.charts.averageLabel', 'Moyenne')}&nbsp;:{' '}
              <span className="font-medium">{Math.round(hrAvg)}</span> bpm
            </span>
          )}
        </div>
        {hasHrData ? (
          <ResponsiveContainer width="100%" height={220}>
            <LineChart data={rows} margin={{ top: 5, right: 12, left: -12, bottom: 0 }}>
              <CartesianGrid strokeDasharray="3 3" opacity={0.3} />
              <XAxis dataKey="label" tick={{ fontSize: 11 }} minTickGap={16} />
              <YAxis tick={{ fontSize: 11 }} />
              <Tooltip
                formatter={value =>
                  value == null
                    ? '—'
                    : `${Math.round(Number(Array.isArray(value) ? value[0] : value))} bpm`
                }
              />
              {hrAvg !== null && (
                <ReferenceLine
                  y={hrAvg}
                  stroke="#6366f1"
                  strokeDasharray="4 4"
                  label={{
                    value: t('healthMetrics.charts.averageLabel', 'Moyenne'),
                    position: 'right',
                    fontSize: 10,
                    fill: '#6366f1',
                  }}
                />
              )}
              <Line
                type="monotone"
                dataKey="heart_rate_avg"
                name={t('healthMetrics.charts.heartRate', 'Fréquence cardiaque')}
                stroke="#ef4444"
                strokeWidth={2}
                dot={{ r: 2 }}
                connectNulls={false}
              />
            </LineChart>
          </ResponsiveContainer>
        ) : (
          <p className="text-sm text-muted-foreground italic py-6 text-center">
            {t('healthMetrics.charts.empty', 'Aucune donnée pour cette période.')}
          </p>
        )}
      </div>

      {/* Steps */}
      <div>
        <div className="flex items-baseline justify-between mb-3">
          <h4 className="text-sm font-semibold">
            {t('healthMetrics.charts.steps', 'Pas par période')}
          </h4>
          {stepsAvg !== null && (
            <span className="text-xs text-muted-foreground">
              {t('healthMetrics.charts.averageLabel', 'Moyenne')}&nbsp;:{' '}
              <span className="font-medium">{Math.round(stepsAvg)}</span>&nbsp;
              {t('healthMetrics.charts.stepsPerDay', '/ jour')}
            </span>
          )}
        </div>
        {hasStepsData ? (
          <ResponsiveContainer width="100%" height={220}>
            <BarChart data={rows} margin={{ top: 5, right: 12, left: -12, bottom: 0 }}>
              <CartesianGrid strokeDasharray="3 3" opacity={0.3} />
              <XAxis dataKey="label" tick={{ fontSize: 11 }} minTickGap={16} />
              <YAxis tick={{ fontSize: 11 }} />
              <Tooltip
                formatter={value =>
                  value == null
                    ? '—'
                    : `${Math.round(Number(Array.isArray(value) ? value[0] : value))} pas`
                }
              />
              {stepsAvg !== null && (
                <ReferenceLine
                  y={stepsAvg}
                  stroke="#10b981"
                  strokeDasharray="4 4"
                  label={{
                    value: t('healthMetrics.charts.averageLabel', 'Moyenne'),
                    position: 'right',
                    fontSize: 10,
                    fill: '#10b981',
                  }}
                />
              )}
              <Bar
                dataKey="steps_total"
                name={t('healthMetrics.charts.steps', 'Pas')}
                fill="#22c55e"
                radius={[4, 4, 0, 0]}
              />
            </BarChart>
          </ResponsiveContainer>
        ) : (
          <p className="text-sm text-muted-foreground italic py-6 text-center">
            {t('healthMetrics.charts.empty', 'Aucune donnée pour cette période.')}
          </p>
        )}
      </div>
    </div>
  );
}
