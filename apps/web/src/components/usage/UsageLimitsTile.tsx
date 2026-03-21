'use client';

import { Clock, Infinity } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { Card, CardContent, CardDescription, CardHeader } from '@/components/ui/card';
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
        <Card
          variant="elevated"
          className="border-2 border-primary/20 bg-gradient-to-br from-primary/5 to-background hover:shadow-xl transition-all"
        >
          <CardHeader className="pb-2">
            <div className="flex items-center justify-between">
              <CardDescription className="text-xs uppercase tracking-wider font-semibold text-primary">
                {t('usage_limits.tile.title_period')}
              </CardDescription>
              <Clock className="h-5 w-5 text-primary" />
            </div>
          </CardHeader>
          <CardContent className="space-y-3">
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
          </CardContent>
        </Card>
      )}

      {/* Absolute limits tile */}
      {hasAbsoluteLimit && (
        <Card
          variant="elevated"
          className="border-2 border-primary/20 bg-gradient-to-br from-primary/5 to-background hover:shadow-xl transition-all"
        >
          <CardHeader className="pb-2">
            <div className="flex items-center justify-between">
              <CardDescription className="text-xs uppercase tracking-wider font-semibold text-primary">
                {t('usage_limits.tile.title_absolute')}
              </CardDescription>
              <Infinity className="h-5 w-5 text-primary" />
            </div>
          </CardHeader>
          <CardContent className="space-y-3">
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
          </CardContent>
        </Card>
      )}
    </>
  );
}
