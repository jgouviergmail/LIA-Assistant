'use client';

import { Heart, HeartPulse, Footprints } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { BriefingCard } from '../BriefingCard';
import { formatNumberLocale } from '@/lib/briefing-utils';
import { cn } from '@/lib/utils';
import type { CardSection, HealthData, HealthSummaryItem } from '@/types/briefing';

interface HealthCardProps {
  section: CardSection<HealthData>;
  isRefreshing: boolean;
  onRefresh: () => void;
  staggerIndex?: number;
}

export function HealthCard({ section, isRefreshing, onRefresh, staggerIndex }: HealthCardProps) {
  return (
    <BriefingCard<HealthData>
      titleKey="dashboard.briefing.cards.health.title"
      icon={<Heart className="h-5 w-5" />}
      tone="red"
      section={section}
      isRefreshing={isRefreshing}
      onRefresh={onRefresh}
      emptyStateKey="dashboard.briefing.cards.health.empty"
      renderContent={data => <HealthContent data={data} />}
      staggerIndex={staggerIndex}
      centerContent
    />
  );
}

function HealthContent({ data }: { data: HealthData }) {
  // Narrow cards stack complete numbers; wider cards align today and average
  // in equal columns. The container query follows the available card width.
  // Each <li> uses `display: contents` so its children participate directly
  // in the parent grid while preserving list semantics for screen readers.
  return (
    <div className="@container w-full max-w-sm">
      <ul className="grid grid-cols-1 items-center justify-items-center gap-x-3 gap-y-2 text-center @min-[20rem]:grid-cols-[minmax(0,1fr)_auto_minmax(0,1fr)]">
        {data.items.map(item => (
          <HealthMetricRow key={item.kind} item={item} />
        ))}
      </ul>
    </div>
  );
}

// Visual thresholds follow the rounded number the card actually displays.
function dailyInk(kind: HealthSummaryItem['kind'], value: number | null): string {
  if (value === null) return 'text-foreground';
  if (kind === 'steps') {
    if (value <= 5000) return 'text-red-700 dark:text-red-300';
    if (value >= 10000) return 'text-green-700 dark:text-green-300';
  } else {
    if (value <= 70) return 'text-green-700 dark:text-green-300';
    if (value >= 90) return 'text-red-700 dark:text-red-300';
  }
  return 'text-orange-700 dark:text-orange-300';
}

function HealthMetricRow({ item }: { item: HealthSummaryItem }) {
  const { t, i18n } = useTranslation();
  const locale = i18n.language || 'fr';
  const Icon = item.kind === 'steps' ? Footprints : HeartPulse;
  const todayValue = item.value_today === null ? null : Math.round(item.value_today);
  const todayLabel = todayValue !== null ? formatNumberLocale(todayValue, locale) : '—';
  const windowLabel =
    item.value_avg_window !== null
      ? formatNumberLocale(Math.round(item.value_avg_window), locale)
      : '—';
  const unitLabel = t(`dashboard.briefing.cards.health.unit_${item.kind}`);

  // contents lets the <li> children participate in the parent grid while
  // keeping correct list semantics in the a11y tree.
  // [&:not(:first-child)>*:first-child] adds top spacing on the header of
  // every metric except the first, without an isFirst prop.
  return (
    <li className="contents [&:not(:first-child)>*:first-child]:mt-7">
      {/* Both metrics share centered, aligned today and average columns. */}
      <div className="col-span-full mb-2 flex items-center justify-center gap-2">
        <Icon className="h-4 w-4 text-red-600 dark:text-red-300 shrink-0" />
        <span className="text-sm font-medium text-foreground/90">
          {t(`dashboard.briefing.cards.health.kind_${item.kind}`)}
        </span>
      </div>

      {/* Today column */}
      <div className="flex min-w-0 flex-col items-center gap-1.5 leading-tight">
        <span
          className={cn(
            'whitespace-nowrap text-4xl font-semibold tabular-nums tracking-tight',
            dailyInk(item.kind, todayValue)
          )}
        >
          {todayLabel}
        </span>
        <span className="text-xs text-muted-foreground">
          {unitLabel} · {t('dashboard.briefing.cards.health.today')}
        </span>
      </div>

      {/* Vertical separator — auto column ensures consistent X position across rows */}
      <div
        className="h-px w-12 bg-border/50 @min-[20rem]:h-full @min-[20rem]:w-px @min-[20rem]:self-stretch"
        aria-hidden="true"
      />

      {/* Window average column */}
      <div className="flex min-w-0 flex-col items-center gap-1.5 leading-tight">
        <span className="text-px-26 font-semibold tabular-nums tracking-tight text-foreground/80">
          {windowLabel}
        </span>
        <span className="text-xs text-muted-foreground">
          {unitLabel} ·{' '}
          {t('dashboard.briefing.cards.health.avg_window', { window: item.window_days })}
        </span>
      </div>
    </li>
  );
}
