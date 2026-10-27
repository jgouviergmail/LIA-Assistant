/** Same psyche history windows and series, with readable responsive controls. */
'use client';

import { useEffect, useId, useMemo, useRef, useState } from 'react';
import { Activity, CalendarDays, Heart, RotateCw, Sparkles, TrendingUp } from 'lucide-react';
import {
  Area,
  AreaChart,
  CartesianGrid,
  Line,
  LineChart,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts';
import { Button } from '@/components/ui/button';
import { useApplicationAccountQuery } from '@/hooks/useApplicationAccountQuery';
import { useApplicationResourceSync } from '@/hooks/useApplicationResourceSync';
import { useTranslation } from '@/i18n/client';
import type { Language } from '@/i18n/settings';
import type { PsycheHistoryEntry } from '@/types/psyche';
import { cn } from '@/lib/utils';
import { toPsycheHistoryData, type PsycheHistoryPoint } from './psyche-history-data';

interface PsycheHistoryProps {
  lng: Language;
  isOpen: boolean;
  refreshKey?: number;
}
type TimeRange = '24h' | '7d' | '30d' | '90d';
type ChartTab = 'pad' | 'emotions' | 'relationship' | 'drives';
const releaseHistoryOverride = () => {};
const EMOTION_COLORS: Record<string, string> = {
  // Positive
  joy: '#34d399', // emerald
  gratitude: '#22d3ee', // cyan
  pride: '#fbbf24', // amber
  amusement: '#f472b6', // pink
  enthusiasm: '#fb923c', // orange
  tenderness: '#ec4899', // pink-hot
  playfulness: '#c084fc', // violet-light
  relief: '#86efac', // green-mint
  wonder: '#fcd34d', // gold
  // Negative
  frustration: '#ef4444', // red
  concern: '#f97316', // orange-dark
  melancholy: '#818cf8', // indigo
  disappointment: '#a855f7', // purple
  nervousness: '#fca5a1', // salmon-pink
  // Neutral
  curiosity: '#a78bfa', // violet
  serenity: '#38bdf8', // sky
  surprise: '#e879f9', // fuchsia (was amber — deduplicated from pride)
  empathy: '#2dd4bf', // teal
  confusion: '#94a3b8', // slate
  determination: '#0ea5e9', // sky-blue (was red — deduplicated from frustration)
  protectiveness: '#14b8a6', // teal-dark
  resolve: '#64748b', // slate-medium
};

const RANGE_HOURS: Record<TimeRange, number> = { '24h': 24, '7d': 168, '30d': 720, '90d': 2160 };
const RANGE_LIMITS: Record<TimeRange, number> = { '24h': 100, '7d': 200, '30d': 300, '90d': 500 };
const ranges: TimeRange[] = ['24h', '7d', '30d', '90d'];
const tabs: ChartTab[] = ['pad', 'emotions', 'relationship', 'drives'];
const TAB_ICONS = { pad: Activity, emotions: Sparkles, relationship: Heart, drives: TrendingUp };
const TAB_KEYS = {
  pad: 'chartPad',
  emotions: 'chartEmotions',
  relationship: 'chartRelationship',
  drives: 'chartDrives',
};
interface ChartSeries {
  key: string;
  label: string;
  color: string;
}

export function PsycheHistory({ lng, isOpen, refreshKey = 0 }: PsycheHistoryProps) {
  const { t } = useTranslation(lng, 'translation');
  const [activeRange, setActiveRange] = useState<TimeRange>('7d');
  const [activeTab, setActiveTab] = useState<ChartTab>('pad');
  const { data, loading, error, refetch, ownerId } = useApplicationAccountQuery<
    PsycheHistoryEntry[]
  >(
    `/psyche/history?limit=${RANGE_LIMITS[activeRange]}&hours=${RANGE_HOURS[activeRange]}`,
    'PsycheHistory',
    isOpen
  );
  useApplicationResourceSync(
    isOpen ? ownerId : undefined,
    'psyche',
    refetch,
    releaseHistoryOverride
  );
  const previousRefresh = useRef(refreshKey);
  useEffect(() => {
    if (!isOpen || previousRefresh.current === refreshKey) return;
    previousRefresh.current = refreshKey;
    void refetch().catch(() => {});
  }, [refreshKey, isOpen, refetch]);
  const history = useMemo(() => toPsycheHistoryData(data ?? []), [data]);
  const chartLabel = t(`psyche.history.${TAB_KEYS[activeTab]}`);
  const rangeLabel = t(`psyche.history.tabs.${activeRange}`);
  const seriesByTab: Record<ChartTab, ChartSeries[]> = {
    pad: [
      { key: 'P', label: t('psyche.education.mood.pleasure'), color: '#0ea5e9' },
      { key: 'A', label: t('psyche.education.mood.arousal'), color: '#d97706' },
      { key: 'D', label: t('psyche.education.mood.dominance'), color: '#8b5cf6' },
    ],
    emotions: history.emotions.map(key => ({
      key,
      label: t(`psyche.emotions.${key.slice(4)}`, key.slice(4)),
      color: EMOTION_COLORS[key.slice(4)] ?? '#64748b',
    })),
    relationship: [
      { key: 'depth', label: t('psyche.depth'), color: '#10b981' },
      { key: 'warmth', label: t('psyche.warmth'), color: '#f97316' },
      { key: 'trust', label: t('psyche.trust'), color: '#0ea5e9' },
    ],
    drives: [
      { key: 'emotionIntensity', label: t('psyche.history.emotionIntensity'), color: '#ec4899' },
      { key: 'curiosity', label: t('psyche.curiosityDrive'), color: '#8b5cf6' },
      { key: 'engagement', label: t('psyche.history.engagement'), color: '#14b8a6' },
    ],
  };
  return (
    <div className="min-w-0 space-y-5">
      <div role="group" aria-label={t('psyche.history.periodLabel')} className="space-y-2">
        <p className="flex items-center gap-2 text-sm font-medium">
          <CalendarDays aria-hidden="true" className="size-4 text-primary" />
          {t('psyche.history.periodLabel')}
        </p>
        <div className="grid grid-cols-4 gap-1 rounded-xl border border-border bg-card p-1">
          {ranges.map(range => (
            <button
              key={range}
              type="button"
              aria-pressed={activeRange === range}
              onClick={() => setActiveRange(range)}
              className={cn(
                'min-w-0 rounded-lg px-1 py-2.5 text-sm transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring',
                activeRange === range
                  ? 'bg-primary/10 font-semibold text-primary'
                  : 'text-muted-foreground hover:bg-muted/60 hover:text-foreground'
              )}
            >
              {t(`psyche.history.tabs.${range}`)}
            </button>
          ))}
        </div>
      </div>
      <div
        role="group"
        aria-label={t('psyche.history.chartLabel')}
        className="grid grid-cols-2 gap-2 sm:grid-cols-4"
      >
        {tabs.map(tab => {
          const Icon = TAB_ICONS[tab];
          return (
            <button
              key={tab}
              type="button"
              aria-pressed={activeTab === tab}
              onClick={() => setActiveTab(tab)}
              className={cn(
                'flex min-w-0 items-center justify-center gap-2 rounded-lg border px-2 py-2.5 text-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring',
                activeTab === tab
                  ? 'border-primary/25 bg-primary/10 font-medium text-primary'
                  : 'border-border bg-card text-muted-foreground hover:bg-muted/40 hover:text-foreground'
              )}
            >
              <Icon aria-hidden="true" className="size-4 shrink-0" />
              <span className="min-w-0 break-words">{t(`psyche.history.${TAB_KEYS[tab]}`)}</span>
            </button>
          );
        })}
      </div>
      {error && (
        <div
          role="alert"
          className="flex flex-col items-start gap-3 rounded-xl border border-destructive/25 bg-destructive/5 p-4 text-sm"
        >
          <p>{t('psyche.history.loadError')}</p>
          <Button
            variant="outline"
            size="sm"
            aria-disabled={loading}
            onClick={() => {
              if (!loading) void refetch().catch(() => {});
            }}
          >
            <RotateCw aria-hidden="true" className="size-4" />
            {t('psyche.history.retry')}
          </Button>
        </div>
      )}
      {loading && !data && (
        <div
          role="status"
          className="flex min-h-64 items-center justify-center rounded-xl bg-card text-sm text-muted-foreground"
        >
          {t('psyche.history.loading')}
        </div>
      )}
      {!loading && !error && history.points.length === 0 && (
        <p className="rounded-xl border border-dashed bg-card px-5 py-12 text-center text-sm text-muted-foreground">
          {t('psyche.history.empty')}
        </p>
      )}
      {history.points.length > 0 && (
        <HistoryChart
          lng={lng}
          label={`${chartLabel} · ${rangeLabel}`}
          activeTab={activeTab}
          data={history.points}
          resets={history.resets}
          series={seriesByTab[activeTab]}
          busy={loading}
        />
      )}
    </div>
  );
}

interface HistoryChartProps {
  lng: Language;
  label: string;
  activeTab: ChartTab;
  data: PsycheHistoryPoint[];
  resets: { time: number; type: string }[];
  series: ChartSeries[];
  busy: boolean;
}
function HistoryChart({ lng, label, activeTab, data, resets, series, busy }: HistoryChartProps) {
  const { t } = useTranslation(lng, 'translation');
  const descriptionId = useId();
  // Keep both snapshots when their timestamps coincide, including after ms parsing.
  const instant = data[0]?.time;
  const timeTicks =
    instant !== undefined && data.every(point => point.time === instant) ? [instant] : undefined;
  const isArea = activeTab === 'emotions' || activeTab === 'drives';
  const Chart = isArea ? AreaChart : LineChart;
  const labels = Object.fromEntries(series.map(item => [item.key, item.label]));
  const dateLabel = (value: number) =>
    new Date(value).toLocaleString(lng, {
      month: 'short',
      day: 'numeric',
      hour: '2-digit',
      minute: '2-digit',
    });
  return (
    <section
      role="region"
      aria-label={label}
      aria-busy={busy}
      aria-describedby={descriptionId}
      className="min-w-0 rounded-xl border border-border bg-card p-2 pt-5 sm:p-4"
    >
      <p id={descriptionId} className="sr-only">
        {t('psyche.history.chartDescription')}
      </p>
      <div className="h-72 min-w-0 sm:h-80">
        <ResponsiveContainer width="100%" height="100%" minWidth={0}>
          <Chart
            data={data}
            accessibilityLayer
            margin={{ top: resets.length ? 25 : 5, right: 12, bottom: 5, left: 0 }}
          >
            <CartesianGrid stroke="var(--color-border)" strokeDasharray="3 5" vertical={false} />
            <XAxis
              dataKey="time"
              type="number"
              scale="time"
              domain={['dataMin', 'dataMax']}
              ticks={timeTicks}
              tickFormatter={dateLabel}
              tick={{ fontSize: 11, fill: 'var(--color-muted-foreground)' }}
              minTickGap={40}
              tickLine={false}
              axisLine={false}
            />
            <YAxis
              domain={activeTab === 'pad' ? [-100, 100] : [0, 100]}
              tick={{ fontSize: 11, fill: 'var(--color-muted-foreground)' }}
              tickLine={false}
              axisLine={false}
              width={42}
              tickFormatter={(value: number) => `${value}%`}
            />
            <Tooltip
              labelFormatter={value => dateLabel(Number(value))}
              contentStyle={{
                fontSize: 12,
                borderRadius: 12,
                border: '1px solid var(--color-border)',
                background: 'var(--color-popover)',
                color: 'var(--color-popover-foreground)',
              }}
              formatter={(value, name) => [`${value}%`, labels[String(name)] ?? String(name)]}
            />
            {activeTab === 'pad' && (
              <ReferenceLine y={0} stroke="var(--color-muted-foreground)" strokeOpacity={0.45} />
            )}
            {series.map(item =>
              isArea ? (
                <Area
                  key={item.key}
                  type="monotone"
                  dataKey={item.key}
                  stroke={item.color}
                  fill={item.color}
                  fillOpacity={0.12}
                  strokeWidth={2}
                  dot={false}
                  connectNulls={activeTab === 'emotions'}
                  isAnimationActive={false}
                />
              ) : (
                <Line
                  key={item.key}
                  type="monotone"
                  dataKey={item.key}
                  stroke={item.color}
                  strokeWidth={2}
                  dot={false}
                  isAnimationActive={false}
                />
              )
            )}
            {resets.map(marker => (
              <ReferenceLine
                key={`${marker.type}-${marker.time}`}
                x={marker.time}
                stroke="var(--color-destructive)"
                strokeDasharray="4 3"
                strokeWidth={1.5}
                label={{
                  value:
                    marker.type === 'reset_full'
                      ? t('psyche.history.resetFull')
                      : t('psyche.history.resetSoft'),
                  position: 'top',
                  fontSize: 10,
                  fill: 'var(--color-destructive)',
                }}
              />
            ))}
          </Chart>
        </ResponsiveContainer>
      </div>
      <ul className="mt-4 flex flex-wrap gap-x-5 gap-y-2 border-t border-border pt-4">
        {series.map(item => (
          <li key={item.key} className="flex min-w-0 items-start gap-2 text-sm">
            <span
              aria-hidden="true"
              className="mt-2 h-0.5 w-4 shrink-0 rounded-full"
              style={{ backgroundColor: item.color }}
            />
            <span className="min-w-0 break-words">{item.label}</span>
          </li>
        ))}
      </ul>
    </section>
  );
}
