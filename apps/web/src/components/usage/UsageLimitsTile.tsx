'use client';

import { Clock, Infinity } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { DashboardTile, TILE_ICON_BADGE } from '@/components/dashboard/DashboardTile';
import { UsageGauge } from '@/components/usage/UsageGauge';
import { formatEuro } from '@/lib/format';
import type { UserUsageLimitResponse } from '@/types/usage-limits';

interface UsageLimitsTileProps {
  /** Usage limits data (null = feature disabled or no limits) */
  limits: UserUsageLimitResponse | null;
  /** Loading state */
  isLoading: boolean;
}

/**
 * Dashboard tiles showing user's usage limits with gauges.
 *
 * Renders up to 2 cards:
 * - Period limits tile (cycle-based, monthly rolling)
 * - Absolute limits tile (lifetime totals)
 *
 * Each tile only renders if at least one limit of that type is defined.
 */
export function UsageLimitsTile({ limits, isLoading }: UsageLimitsTileProps) {
  const { t } = useTranslation();

  if (!limits || isLoading) return null;

  const hasCycleLimit =
    limits.cycle_tokens.limit !== null ||
    limits.cycle_messages.limit !== null ||
    limits.cycle_cost.limit !== null;

  const hasAbsoluteLimit =
    limits.absolute_tokens.limit !== null ||
    limits.absolute_messages.limit !== null ||
    limits.absolute_cost.limit !== null;

  if (!hasCycleLimit && !hasAbsoluteLimit) return null;

  return (
    <>
      {/* Period limits tile */}
      {hasCycleLimit && (
        <DashboardTile contentClassName="space-y-3 p-5 sm:p-6">
          <TileHeading
            icon={<Clock className="h-5 w-5" />}
            title={t('usage_limits.tile.title_period')}
          />
          <div className="space-y-3">
            {limits.cycle_messages.limit !== null && (
              <UsageGauge
                detail={limits.cycle_messages}
                label={t('usage_limits.tile.messages')}
                mode="period"
                t={t}
                size="sm"
              />
            )}
            {limits.cycle_tokens.limit !== null && (
              <UsageGauge
                detail={limits.cycle_tokens}
                label={t('usage_limits.tile.tokens')}
                mode="period"
                t={t}
                size="sm"
              />
            )}
            {limits.cycle_cost.limit !== null && (
              <UsageGauge
                detail={limits.cycle_cost}
                label={t('usage_limits.tile.cost')}
                mode="period"
                formatValue={v => formatEuro(v, 2)}
                t={t}
                size="sm"
              />
            )}
          </div>
        </DashboardTile>
      )}

      {/* Absolute limits tile */}
      {hasAbsoluteLimit && (
        <DashboardTile contentClassName="space-y-3 p-5 sm:p-6">
          <TileHeading
            icon={<Infinity className="h-5 w-5" />}
            title={t('usage_limits.tile.title_absolute')}
          />
          <div className="space-y-3">
            {limits.absolute_messages.limit !== null && (
              <UsageGauge
                detail={limits.absolute_messages}
                label={t('usage_limits.tile.messages')}
                mode="absolute"
                t={t}
                size="sm"
              />
            )}
            {limits.absolute_tokens.limit !== null && (
              <UsageGauge
                detail={limits.absolute_tokens}
                label={t('usage_limits.tile.tokens')}
                mode="absolute"
                t={t}
                size="sm"
              />
            )}
            {limits.absolute_cost.limit !== null && (
              <UsageGauge
                detail={limits.absolute_cost}
                label={t('usage_limits.tile.cost')}
                mode="absolute"
                formatValue={v => formatEuro(v, 2)}
                t={t}
                size="sm"
              />
            )}
          </div>
        </DashboardTile>
      )}
    </>
  );
}

/** Badge + title, as at the head of every dashboard tile (DashboardTile). */
function TileHeading({ icon, title }: { icon: React.ReactNode; title: string }) {
  return (
    <div className="flex items-center gap-3">
      <span className={TILE_ICON_BADGE} aria-hidden="true">
        {icon}
      </span>
      <h3 className="truncate text-sm font-semibold tracking-tight text-primary">{title}</h3>
    </div>
  );
}
