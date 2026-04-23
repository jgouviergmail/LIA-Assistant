'use client';

import { Heart, Footprints } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { BriefingCard } from '../BriefingCard';
import { formatNumberLocale } from '@/lib/briefing-utils';
import type { CardSection, HealthData, HealthSummaryItem } from '@/types/briefing';

interface HealthCardProps {
  section: CardSection<HealthData>;
  isRefreshing: boolean;
  onRefresh: () => void;
  staggerIndex?: number;
}

export function HealthCard({
  section,
  isRefreshing,
  onRefresh,
  staggerIndex,
}: HealthCardProps) {
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
  // Single CSS grid shared by all metrics so the [today | sep | avg] columns
  // line up vertically across rows (1fr auto 1fr → equal value columns,
  // identical separator position regardless of label widths).
  // Each <li> uses `display: contents` so its children participate directly
  // in the parent grid while preserving list semantics for screen readers.
  return (
    <ul className="grid grid-cols-[minmax(0,1fr)_auto_minmax(0,1fr)] items-baseline gap-x-3 gap-y-1">
      {data.items.map(item => (
        <HealthMetricRow key={item.kind} item={item} />
      ))}
    </ul>
  );
}

function HealthMetricRow({ item }: { item: HealthSummaryItem }) {
  const { t, i18n } = useTranslation();
  const locale = i18n.language || 'fr';
  const Icon = item.kind === 'steps' ? Footprints : Heart;
  const todayLabel =
    item.value_today !== null
      ? formatNumberLocale(Math.round(item.value_today), locale)
      : '—';
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
      {/* Header row — spans the 3 columns, centered */}
      <div className="col-span-3 flex items-center justify-center gap-2">
        <Icon className="h-4 w-4 text-red-600 dark:text-red-300 shrink-0" />
        <span className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">
          {t(`dashboard.briefing.cards.health.kind_${item.kind}`)}
        </span>
      </div>

      {/* Today column */}
      <div className="flex flex-col items-end leading-tight">
        <span className="text-base font-bold tabular-nums text-foreground">
          {todayLabel}
          <span className="ml-1 text-xs font-normal text-muted-foreground">
            {unitLabel}
          </span>
        </span>
        <span className="text-[10px] uppercase tracking-wide text-muted-foreground/70">
          {t('dashboard.briefing.cards.health.today')}
        </span>
      </div>

      {/* Vertical separator — auto column ensures consistent X position across rows */}
      <div className="h-7 w-px self-center bg-border/50" aria-hidden="true" />

      {/* Window average column */}
      <div className="flex flex-col items-start leading-tight">
        <span className="text-base font-bold tabular-nums text-foreground/80">
          {windowLabel}
          <span className="ml-1 text-xs font-normal text-muted-foreground">
            {unitLabel}
          </span>
        </span>
        <span className="text-[10px] uppercase tracking-wide text-muted-foreground/70">
          {t('dashboard.briefing.cards.health.avg_window', { window: item.window_days })}
        </span>
      </div>
    </li>
  );
}
