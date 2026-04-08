/**
 * PsycheHistory — graphical evolution dashboard for psyche metrics.
 *
 * Displays PAD mood, emotions, and relationship metrics over time
 * using recharts line/area charts with time range selector.
 *
 * Phase: evolution — Psyche Engine (Iteration 3)
 * Created: 2026-04-01
 */

'use client';

import { useMemo, useState } from 'react';
import {
  Area,
  AreaChart,
  CartesianGrid,
  Legend,
  Line,
  LineChart,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts';

import { useApiQuery } from '@/hooks/useApiQuery';
import { useTranslation } from '@/i18n/client';
import type { Language } from '@/i18n/settings';
import type { PsycheHistoryEntry } from '@/types/psyche';
import { cn } from '@/lib/utils';

interface PsycheHistoryProps {
  lng: Language;
  isOpen: boolean;
}

type TimeRange = '24h' | '7d' | '30d' | '90d';

/** Stable color per emotion — positive=green tones, negative=red tones, neutral=blue/gray. */
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

const RANGE_HOURS: Record<TimeRange, number> = {
  '24h': 24,
  '7d': 168,
  '30d': 720,
  '90d': 2160,
};

const RANGE_LIMITS: Record<TimeRange, number> = {
  '24h': 100,
  '7d': 200,
  '30d': 300,
  '90d': 500,
};

type ChartTab = 'pad' | 'emotions' | 'relationship' | 'drives';

export function PsycheHistory({ lng, isOpen }: PsycheHistoryProps) {
  const { t } = useTranslation(lng, 'translation');
  const [activeRange, setActiveRange] = useState<TimeRange>('7d');
  const [activeTab, setActiveTab] = useState<ChartTab>('pad');

  const { data, loading } = useApiQuery<PsycheHistoryEntry[]>(
    `/psyche/history?limit=${RANGE_LIMITS[activeRange]}&hours=${RANGE_HOURS[activeRange]}`,
    {
      componentName: 'PsycheHistory',
      enabled: isOpen,
    }
  );

  // Extract reset markers (vertical reference lines on charts)
  const resetMarkers = useMemo(() => {
    if (!data || data.length === 0) return [];
    return data
      .filter(e => e.snapshot_type.startsWith('reset_'))
      .map(e => ({
        time: new Date(e.created_at).getTime(),
        label:
          e.snapshot_type === 'reset_full'
            ? t('psyche.history.resetFull', 'Full reset')
            : t('psyche.history.resetSoft', 'Mood refresh'),
      }));
  }, [data, t]);

  // Transform data for recharts (reverse to chronological order, exclude reset snapshots)
  const chartData = useMemo(() => {
    if (!data || data.length === 0) return [];
    return [...data]
      .filter(e => !e.snapshot_type.startsWith('reset_'))
      .reverse()
      .map(entry => {
        const date = new Date(entry.created_at);
        return {
          time: date.getTime(),
          timeLabel: date.toLocaleString(lng, {
            month: 'short',
            day: 'numeric',
            hour: '2-digit',
            minute: '2-digit',
          }),
          // PAD as percentages
          P: Math.round(entry.mood_pleasure * 100),
          A: Math.round(entry.mood_arousal * 100),
          D: Math.round(entry.mood_dominance * 100),
          // Per-emotion intensities (from active_emotions map in trait_snapshot)
          ...Object.fromEntries(
            Object.entries(
              (entry.trait_snapshot?.active_emotions as Record<string, number> | undefined) ?? {}
            ).map(([emo, intensity]) => [`emo_${emo}`, Math.round((intensity as number) * 100)])
          ),
          // Fallback: if no active_emotions map, use dominant_emotion + intensity
          ...(!entry.trait_snapshot?.active_emotions && entry.dominant_emotion
            ? {
                [`emo_${entry.dominant_emotion}`]: Math.round(
                  (entry.trait_snapshot?.emotion_intensity ?? 0) * 100
                ),
              }
            : {}),
          // Dominant emotion intensity (for drives chart)
          emotionIntensity: Math.round((entry.trait_snapshot?.emotion_intensity ?? 0) * 100),
          // Relationship + Drives
          depth: Math.round((entry.trait_snapshot?.relationship_depth ?? 0) * 100),
          warmth: Math.round((entry.trait_snapshot?.relationship_warmth ?? 0) * 100),
          trust: Math.round((entry.trait_snapshot?.relationship_trust ?? 0) * 100),
          curiosity: Math.round((entry.trait_snapshot?.drive_curiosity ?? 0) * 100),
          engagement: Math.round((entry.trait_snapshot?.drive_engagement ?? 0) * 100),
        };
      });
  }, [data, lng]);

  // Discover all emotions that appear in the dataset (for dynamic chart lines)
  const emotionKeys = useMemo(() => {
    const keys = new Set<string>();
    for (const point of chartData) {
      for (const key of Object.keys(point)) {
        if (key.startsWith('emo_')) keys.add(key);
      }
    }
    return Array.from(keys).sort();
  }, [chartData]);

  const ranges: TimeRange[] = ['24h', '7d', '30d', '90d'];
  const tabs: ChartTab[] = ['pad', 'emotions', 'relationship', 'drives'];

  return (
    <div className="space-y-3">
      {/* Time range selector */}
      <div className="flex gap-1 rounded-lg bg-muted p-0.5">
        {ranges.map(range => (
          <button
            key={range}
            onClick={() => setActiveRange(range)}
            className={cn(
              'flex-1 text-xs py-1 rounded-md transition-colors',
              activeRange === range
                ? 'bg-background text-foreground shadow-sm font-medium'
                : 'text-muted-foreground hover:text-foreground'
            )}
          >
            {t(`psyche.history.tabs.${range}`, range)}
          </button>
        ))}
      </div>

      {/* Chart tab selector */}
      <div className="flex gap-1 rounded-lg bg-muted/50 p-0.5">
        {tabs.map(tab => (
          <button
            key={tab}
            onClick={() => setActiveTab(tab)}
            className={cn(
              'flex-1 text-xs py-1 rounded-md transition-colors',
              activeTab === tab
                ? 'bg-background text-foreground shadow-sm font-medium'
                : 'text-muted-foreground hover:text-foreground'
            )}
          >
            {tab === 'pad'
              ? t('psyche.history.chartPad', 'Mood (PAD)')
              : tab === 'emotions'
                ? t('psyche.history.chartEmotions', 'Emotions')
                : tab === 'relationship'
                  ? t('psyche.history.chartRelationship', 'Relationship')
                  : t('psyche.history.chartDrives', 'Drives')}
          </button>
        ))}
      </div>

      {/* Chart */}
      {loading && (
        <div className="h-48 flex items-center justify-center">
          <div className="animate-pulse text-xs text-muted-foreground">
            {t('psyche.history.loading', 'Loading...')}
          </div>
        </div>
      )}

      {!loading && chartData.length === 0 && (
        <p className="text-xs text-muted-foreground italic text-center py-8">
          {t('psyche.history.empty', 'No history available for this period')}
        </p>
      )}

      {!loading && chartData.length > 0 && (
        <div className="h-52">
          <ResponsiveContainer width="100%" height="100%">
            {activeTab === 'pad' ? (
              <LineChart data={chartData}>
                <CartesianGrid strokeDasharray="3 3" opacity={0.15} />
                <XAxis
                  dataKey="timeLabel"
                  tick={{ fontSize: 9 }}
                  interval="preserveStartEnd"
                  tickLine={false}
                />
                <YAxis
                  domain={[-100, 100]}
                  tick={{ fontSize: 9 }}
                  tickLine={false}
                  width={35}
                  tickFormatter={(v: number) => `${v}%`}
                />
                <Tooltip
                  contentStyle={{
                    fontSize: 11,
                    borderRadius: 8,
                    border: '1px solid hsl(var(--border))',
                    background: 'hsl(var(--popover))',
                    color: 'hsl(var(--popover-foreground))',
                  }}
                  formatter={(value, name) => {
                    const padLabels: Record<string, string> = {
                      P: t('psyche.education.mood.pleasure', 'Pleasure'),
                      A: t('psyche.education.mood.arousal', 'Arousal'),
                      D: t('psyche.education.mood.dominance', 'Dominance'),
                    };
                    const key = String(name ?? '');
                    return [`${value}%`, padLabels[key] || key];
                  }}
                />
                <Legend
                  wrapperStyle={{ fontSize: 10 }}
                  formatter={(value: string) => {
                    const padLabels: Record<string, string> = {
                      P: t('psyche.education.mood.pleasure', 'Pleasure'),
                      A: t('psyche.education.mood.arousal', 'Arousal'),
                      D: t('psyche.education.mood.dominance', 'Dominance'),
                    };
                    return padLabels[value] || value;
                  }}
                />
                <Line type="monotone" dataKey="P" stroke="#38bdf8" strokeWidth={2} dot={false} />
                <Line type="monotone" dataKey="A" stroke="#fbbf24" strokeWidth={2} dot={false} />
                <Line type="monotone" dataKey="D" stroke="#a78bfa" strokeWidth={2} dot={false} />
                {resetMarkers.map((m, i) => (
                  <ReferenceLine
                    key={`reset-pad-${i}`}
                    x={chartData.find(d => d.time >= m.time)?.timeLabel}
                    stroke="#ef4444"
                    strokeDasharray="4 2"
                    strokeWidth={1.5}
                    label={{ value: m.label, position: 'top', fontSize: 8, fill: '#ef4444' }}
                  />
                ))}
              </LineChart>
            ) : activeTab === 'emotions' ? (
              <AreaChart data={chartData}>
                <CartesianGrid strokeDasharray="3 3" opacity={0.15} />
                <XAxis
                  dataKey="timeLabel"
                  tick={{ fontSize: 9 }}
                  interval="preserveStartEnd"
                  tickLine={false}
                />
                <YAxis
                  domain={[0, 100]}
                  tick={{ fontSize: 9 }}
                  tickLine={false}
                  width={35}
                  tickFormatter={(v: number) => `${v}%`}
                />
                <Tooltip
                  contentStyle={{
                    fontSize: 11,
                    borderRadius: 8,
                    border: '1px solid hsl(var(--border))',
                    background: 'hsl(var(--popover))',
                    color: 'hsl(var(--popover-foreground))',
                  }}
                  formatter={(value, name) => {
                    const emoName = String(name ?? '').replace('emo_', '');
                    return [`${value}%`, String(t(`psyche.emotions.${emoName}`, emoName))];
                  }}
                />
                <Legend
                  wrapperStyle={{ fontSize: 10 }}
                  formatter={(value: string) => {
                    const emoName = value.replace('emo_', '');
                    return t(`psyche.emotions.${emoName}`, emoName);
                  }}
                />
                {emotionKeys.map(key => {
                  const color = EMOTION_COLORS[key.replace('emo_', '')] ?? '#9ca3af';
                  return (
                    <Area
                      key={key}
                      type="monotone"
                      dataKey={key}
                      stroke={color}
                      fill={color}
                      fillOpacity={0.15}
                      strokeWidth={1.5}
                      dot={false}
                      connectNulls
                    />
                  );
                })}
                {resetMarkers.map((m, i) => (
                  <ReferenceLine
                    key={`reset-emo-${i}`}
                    x={chartData.find(d => d.time >= m.time)?.timeLabel}
                    stroke="#ef4444"
                    strokeDasharray="4 2"
                    strokeWidth={1.5}
                    label={{ value: m.label, position: 'top', fontSize: 8, fill: '#ef4444' }}
                  />
                ))}
              </AreaChart>
            ) : activeTab === 'relationship' ? (
              <LineChart data={chartData}>
                <CartesianGrid strokeDasharray="3 3" opacity={0.15} />
                <XAxis
                  dataKey="timeLabel"
                  tick={{ fontSize: 9 }}
                  interval="preserveStartEnd"
                  tickLine={false}
                />
                <YAxis
                  domain={[0, 100]}
                  tick={{ fontSize: 9 }}
                  tickLine={false}
                  width={35}
                  tickFormatter={(v: number) => `${v}%`}
                />
                <Tooltip
                  contentStyle={{
                    fontSize: 11,
                    borderRadius: 8,
                    border: '1px solid hsl(var(--border))',
                    background: 'hsl(var(--popover))',
                    color: 'hsl(var(--popover-foreground))',
                  }}
                  formatter={(value, name) => {
                    const labels: Record<string, string> = {
                      depth: t('psyche.depth', 'Depth'),
                      warmth: t('psyche.warmth', 'Warmth'),
                      trust: t('psyche.trust', 'Trust'),
                    };
                    const key = String(name ?? '');
                    return [`${value}%`, labels[key] || key];
                  }}
                />
                <Legend
                  wrapperStyle={{ fontSize: 10 }}
                  formatter={(value: string) => {
                    const labels: Record<string, string> = {
                      depth: t('psyche.depth', 'Depth'),
                      warmth: t('psyche.warmth', 'Warmth'),
                      trust: t('psyche.trust', 'Trust'),
                    };
                    return labels[value] || value;
                  }}
                />
                <Line
                  type="monotone"
                  dataKey="depth"
                  stroke="#34d399"
                  strokeWidth={2}
                  dot={false}
                />
                <Line
                  type="monotone"
                  dataKey="warmth"
                  stroke="#f97316"
                  strokeWidth={2}
                  dot={false}
                />
                <Line
                  type="monotone"
                  dataKey="trust"
                  stroke="#38bdf8"
                  strokeWidth={2}
                  dot={false}
                />
                {resetMarkers.map((m, i) => (
                  <ReferenceLine
                    key={`reset-rel-${i}`}
                    x={chartData.find(d => d.time >= m.time)?.timeLabel}
                    stroke="#ef4444"
                    strokeDasharray="4 2"
                    strokeWidth={1.5}
                    label={{ value: m.label, position: 'top', fontSize: 8, fill: '#ef4444' }}
                  />
                ))}
              </LineChart>
            ) : (
              <AreaChart data={chartData}>
                <CartesianGrid strokeDasharray="3 3" opacity={0.15} />
                <XAxis
                  dataKey="timeLabel"
                  tick={{ fontSize: 9 }}
                  interval="preserveStartEnd"
                  tickLine={false}
                />
                <YAxis
                  domain={[0, 100]}
                  tick={{ fontSize: 9 }}
                  tickLine={false}
                  width={35}
                  tickFormatter={(v: number) => `${v}%`}
                />
                <Tooltip
                  contentStyle={{
                    fontSize: 11,
                    borderRadius: 8,
                    border: '1px solid hsl(var(--border))',
                    background: 'hsl(var(--popover))',
                    color: 'hsl(var(--popover-foreground))',
                  }}
                  formatter={(value, name) => {
                    const labels: Record<string, string> = {
                      curiosity: t('psyche.curiosityDrive', 'Curiosity'),
                      engagement: t('psyche.history.engagement', 'Engagement'),
                      emotionIntensity: t('psyche.history.emotionIntensity', 'Emotion intensity'),
                    };
                    const key = String(name ?? '');
                    return [`${value}%`, labels[key] || key];
                  }}
                />
                <Legend
                  wrapperStyle={{ fontSize: 10 }}
                  formatter={(value: string) => {
                    const labels: Record<string, string> = {
                      curiosity: t('psyche.curiosityDrive', 'Curiosity'),
                      engagement: t('psyche.history.engagement', 'Engagement'),
                      emotionIntensity: t('psyche.history.emotionIntensity', 'Emotion intensity'),
                    };
                    return labels[value] || value;
                  }}
                />
                <Area
                  type="monotone"
                  dataKey="emotionIntensity"
                  stroke="#f472b6"
                  fill="#f472b6"
                  fillOpacity={0.15}
                  strokeWidth={2}
                  dot={false}
                />
                <Area
                  type="monotone"
                  dataKey="curiosity"
                  stroke="#a78bfa"
                  fill="#a78bfa"
                  fillOpacity={0.1}
                  strokeWidth={1.5}
                  dot={false}
                />
                <Area
                  type="monotone"
                  dataKey="engagement"
                  stroke="#2dd4bf"
                  fill="#2dd4bf"
                  fillOpacity={0.1}
                  strokeWidth={1.5}
                  dot={false}
                />
                {resetMarkers.map((m, i) => (
                  <ReferenceLine
                    key={`reset-drv-${i}`}
                    x={chartData.find(d => d.time >= m.time)?.timeLabel}
                    stroke="#ef4444"
                    strokeDasharray="4 2"
                    strokeWidth={1.5}
                    label={{ value: m.label, position: 'top', fontSize: 8, fill: '#ef4444' }}
                  />
                ))}
              </AreaChart>
            )}
          </ResponsiveContainer>
        </div>
      )}
    </div>
  );
}
