'use client';

import { Heart, HeartPulse, Footprints } from '@/lib/icons';
import { useTranslation } from 'react-i18next';
import { BriefingCard } from '../BriefingCard';
import { HealthDial, HEALTH_TONE_INK } from './HealthDial';
import { formatNumberLocale } from '@/lib/briefing-utils';
import { HEALTH_SCALES, toneOf } from '@/lib/health-dial';
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
  // Two measures stand side by side, the same shape on each side, so neither outweighs the other;
  // a card too narrow for that stacks them, and a measure alone keeps the middle. The container
  // query follows the card's width. Each measure spans three rows of the list's grid, so the
  // dials stay level whichever title takes two lines.
  return (
    <div className="@container w-full">
      <ul
        className={cn(
          'mx-auto grid grid-cols-1 justify-items-center gap-x-3 gap-y-6 text-center',
          data.items.length > 1 ? '@min-[14rem]:grid-cols-2' : 'max-w-56'
        )}
      >
        {data.items.map(item => (
          <HealthMetric key={item.kind} item={item} />
        ))}
      </ul>
    </div>
  );
}

// Visual thresholds follow the rounded number the card actually displays.
function dailyInk(kind: HealthSummaryItem['kind'], value: number | null): string {
  if (value === null) return 'text-foreground';
  return HEALTH_TONE_INK[toneOf(HEALTH_SCALES[kind], value)];
}

function HealthMetric({ item }: { item: HealthSummaryItem }) {
  const { t, i18n } = useTranslation();
  const locale = i18n.language || 'fr';
  const Icon = item.kind === 'steps' ? Footprints : HeartPulse;
  const todayValue = item.value_today === null ? null : Math.round(item.value_today);
  const averageValue = item.value_avg_window === null ? null : Math.round(item.value_avg_window);
  const todayLabel = todayValue !== null ? formatNumberLocale(todayValue, locale) : '—';
  const windowLabel = averageValue !== null ? formatNumberLocale(averageValue, locale) : '—';
  const unitLabel = t(`dashboard.briefing.cards.health.unit_${item.kind}`);

  return (
    <li className="row-span-3 grid w-full min-w-0 grid-rows-subgrid justify-items-center gap-y-2">
      <span className="text-sm font-medium leading-tight text-foreground/90">
        {t(`dashboard.briefing.cards.health.kind_${item.kind}`)}
      </span>

      {/* Today: its figure in the dial, the figure's unit and day just under it. */}
      <div className="flex w-full min-w-0 flex-col items-center gap-1 leading-tight">
        <HealthDial kind={item.kind} today={todayValue} average={averageValue}>
          <Icon className="h-5 w-5 shrink-0 text-red-600 dark:text-red-300" aria-hidden="true" />
          <span
            className={cn(
              'whitespace-nowrap text-[clamp(1.125rem,20cqw,2.25rem)] font-semibold leading-none tracking-tight',
              dailyInk(item.kind, todayValue)
            )}
          >
            {todayLabel}
          </span>
        </HealthDial>
        <span className="text-xs text-muted-foreground">
          {unitLabel} · {t('dashboard.briefing.cards.health.today')}
        </span>
      </div>

      {/* The window's average, marked by the notch it wears on the dial. */}
      <div className="flex min-w-0 flex-wrap items-baseline justify-center gap-x-1.5 leading-tight">
        {averageValue !== null && (
          <span
            aria-hidden="true"
            className="h-3 w-0.5 shrink-0 self-center rounded-full bg-foreground/70"
            data-testid="health-average-key"
          />
        )}
        <span className="whitespace-nowrap text-base font-semibold tracking-tight text-foreground/80">
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
