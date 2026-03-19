/**
 * Token Budget Section Component
 *
 * Displays the LLM context token budget usage.
 * Includes fallback strategy display with proper labeling.
 */

import React from 'react';
import { AccordionItem, AccordionTrigger, AccordionContent } from '@/components/ui/accordion';
import { MetricRow, ZoneBadge } from '../shared';
import {
  getZoneColor,
  TOKEN_BAR_HEIGHT,
  FALLBACK_STRATEGY_LABELS,
  FALLBACK_STRATEGY_COLORS,
} from '../../utils/constants';
import { formatTokenCount } from '../../utils/formatters';
import { cn } from '@/lib/utils';
import type { DebugMetrics } from '@/types/chat';

export interface TokenBudgetSectionProps {
  /** Token budget metrics (can be undefined) */
  data: DebugMetrics['token_budget'];
}

/** French labels for zones */
const ZONE_LABELS: Record<string, string> = {
  safe: 'Sûr',
  warning: 'Attention',
  critical: 'Critique',
  emergency: 'Urgence',
};

/** Dark mode compatible classes for zones */
const ZONE_TEXT_COLORS: Record<string, string> = {
  safe: 'text-green-400',
  warning: 'text-yellow-400',
  critical: 'text-orange-400',
  emergency: 'text-red-400',
};

/**
 * Section Token Budget
 *
 * Clearly displays:
 * - Current token budget usage
 * - Risk zone (safe, warning, critical, emergency)
 * - Active fallback strategy
 * - Visual progress bar
 * - Thresholds for each zone
 */
export const TokenBudgetSection = React.memo(function TokenBudgetSection({
  data,
}: TokenBudgetSectionProps) {
  if (!data) {
    return null;
  }

  const {
    current_tokens,
    thresholds,
    zone,
    strategy,
    fallback_active,
    // v3.1: Real token consumption from LLM calls
    total_consumed,
    tokens_input,
    tokens_output,
    tokens_cache,
  } = data;
  const progressPercentage =
    thresholds.max > 0 ? Math.min((current_tokens / thresholds.max) * 100, 100) : 0;

  // Get strategy label and color
  const strategyLabel = strategy ? FALLBACK_STRATEGY_LABELS[strategy] || strategy : null;
  const strategyColor = strategy
    ? FALLBACK_STRATEGY_COLORS[strategy] || 'bg-muted text-muted-foreground border-border'
    : null;

  return (
    <AccordionItem value="token_budget">
      <AccordionTrigger className="py-2 text-sm">
        <div className="flex items-center gap-2">
          <span>Token Budget</span>
          <ZoneBadge zone={zone} size="xs" />
        </div>
      </AccordionTrigger>
      <AccordionContent>
        <div className="space-y-3">
          {/* Actual total consumed (v3.1 - includes response) */}
          {total_consumed !== undefined && (
            <div className="space-y-1">
              <div className="text-xs text-muted-foreground font-medium mb-1">
                Total consommé (réel)
              </div>
              <MetricRow
                label="Total"
                value={formatTokenCount(total_consumed)}
                highlight
                valueClassName="text-primary font-bold"
              />
              <div className="grid grid-cols-3 gap-1 text-[10px]">
                <div className="flex flex-col items-center p-1 rounded bg-muted/30">
                  <span className="text-muted-foreground">Input</span>
                  <span className="font-medium text-foreground">
                    {formatTokenCount(tokens_input || 0)}
                  </span>
                </div>
                <div className="flex flex-col items-center p-1 rounded bg-muted/30">
                  <span className="text-muted-foreground">Output</span>
                  <span className="font-medium text-foreground">
                    {formatTokenCount(tokens_output || 0)}
                  </span>
                </div>
                <div className="flex flex-col items-center p-1 rounded bg-muted/30">
                  <span className="text-muted-foreground">Cache</span>
                  <span className="font-medium text-green-400">
                    {formatTokenCount(tokens_cache || 0)}
                  </span>
                </div>
              </div>
            </div>
          )}

          {/* Current context (for zone calculation) */}
          <div className="space-y-1 border-t border-border/50 pt-2">
            <div className="text-xs text-muted-foreground font-medium mb-1">Taille du contexte</div>
            <MetricRow
              label="Tokens contexte"
              value={`${formatTokenCount(current_tokens)} / ${formatTokenCount(thresholds.max)}`}
            />
            <MetricRow
              label="Zone"
              value={ZONE_LABELS[zone] || zone}
              valueClassName={cn(ZONE_TEXT_COLORS[zone] || 'text-foreground', 'font-medium')}
            />
          </div>

          {/* Fallback strategy */}
          {strategy && (
            <div className="border-t border-border/50 pt-2 space-y-1">
              <div className="text-xs text-muted-foreground font-medium mb-1">
                Stratégie catalogue
              </div>
              <div className="flex items-center gap-2">
                <span
                  className={cn(
                    'text-[10px] px-2 py-0.5 rounded border font-medium',
                    strategyColor
                  )}
                >
                  {strategyLabel}
                </span>
                {fallback_active && (
                  <span className="text-[10px] text-yellow-400 italic">(mode dégradé)</span>
                )}
              </div>
            </div>
          )}

          {/* Visual progress bar */}
          <div className="border-t border-border/50 pt-2">
            <div className="text-xs text-muted-foreground font-medium mb-2">
              Progression du budget
            </div>
            <div className="relative">
              <div
                className="w-full bg-muted rounded-full overflow-hidden"
                style={{ height: TOKEN_BAR_HEIGHT }}
              >
                <div
                  className={`h-full transition-all ${getZoneColor(zone, 'bar')}`}
                  style={{ width: `${progressPercentage}%` }}
                />
              </div>
              <div className="flex justify-between mt-1 text-[10px] text-muted-foreground">
                <span>0</span>
                <span className={cn('font-medium', ZONE_TEXT_COLORS[zone])}>
                  {Math.round(progressPercentage)}%
                </span>
                <span>{formatTokenCount(thresholds.max)}</span>
              </div>
            </div>
          </div>

          {/* Zone thresholds */}
          <div className="border-t border-border/50 pt-2">
            <div className="text-xs text-muted-foreground font-medium mb-1.5">Seuils des zones</div>
            <div className="grid grid-cols-2 gap-x-4 gap-y-1">
              <MetricRow
                label="Sûr"
                value={`< ${formatTokenCount(thresholds.safe)}`}
                valueClassName="text-green-400"
              />
              <MetricRow
                label="Attention"
                value={`< ${formatTokenCount(thresholds.warning)}`}
                valueClassName="text-yellow-400"
              />
              <MetricRow
                label="Critique"
                value={`< ${formatTokenCount(thresholds.critical)}`}
                valueClassName="text-orange-400"
              />
              <MetricRow
                label="Maximum"
                value={formatTokenCount(thresholds.max)}
                valueClassName="text-red-400"
              />
            </div>
          </div>
        </div>
      </AccordionContent>
    </AccordionItem>
  );
});
