/**
 * Token Budget Section Component
 *
 * Displays the LLM context token budget usage.
 * Includes fallback strategy display with proper labeling.
 */

import React from 'react';
import { Gauge } from 'lucide-react';
import {
  DebugChip,
  DebugSection,
  EmptySection,
  MetricRow,
  SubSectionHeader,
  ZoneBadge,
} from '../shared';
import { FALLBACK_STRATEGY_LABELS } from '../../utils/constants';
import { TONE_BAR, TONE_TEXT, fallbackLevelTone, zoneTone } from '../../utils/tones';
import { formatTokenCount } from '../../utils/formatters';
import { cn } from '@/lib/utils';
import type { DebugMetrics } from '@/types/chat';

export interface TokenBudgetSectionProps {
  /** Token budget metrics (can be undefined) */
  data: DebugMetrics['token_budget'];
}

/**
 * Who answered when the window was resolved (ADR-278, B8).
 *
 * Named rather than shown raw because the three are not equally trustworthy:
 * the table is a safety net, not a declaration.
 */
const WINDOW_SOURCE_LABELS: Record<string, string> = {
  slot_override: 'Operator override',
  catalogue: 'Model catalogue',
  table: 'Fallback table',
};

/** English display labels for zones */
const ZONE_LABELS: Record<string, string> = {
  safe: 'Safe',
  warning: 'Warning',
  critical: 'Critical',
  emergency: 'Emergency',
};

/**
 * The room the turn actually had (ADR-278, B8).
 *
 * Its own component so the section stays under the complexity cap, and because
 * this block answers a different question from the zones below it: the zones
 * are instance-wide settings, this is the model's own bound.
 *
 * @param props.window - The effective context window, or undefined on a payload
 *   persisted before B8 — in which case nothing is drawn rather than a zero.
 * @param props.source - Which of the three sources answered.
 * @param props.model - The model the window belongs to.
 * @param props.usedPercent - How much of it the turn used.
 * @param props.compactionThreshold - The instant compaction fires.
 * @param props.compactionSource - Whether that instant was pinned or derived.
 * @returns The block, or null.
 */
function ModelWindow({
  window,
  source,
  model,
  usedPercent,
  compactionThreshold,
  compactionSource,
}: {
  window: number | undefined;
  source: string | undefined;
  model: string | undefined;
  usedPercent: number | undefined;
  compactionThreshold: number | undefined;
  compactionSource: string | undefined;
}) {
  if (window === undefined) return null;
  return (
    <div className="space-y-1">
      <SubSectionHeader label="Model window" borderTop />
      <MetricRow label="Context window" value={formatTokenCount(window)} highlight />
      {model && <MetricRow label="Model" value={model} mono />}
      {source && (
        <MetricRow
          label="Declared by"
          value={WINDOW_SOURCE_LABELS[source] ?? source}
          /* A window from the hand-maintained table is a DEFAULT, not a
             measurement: that table is wrong on 10 of its 56 entries. */
          valueClassName={source === 'table' ? TONE_TEXT.warning : undefined}
        />
      )}
      {usedPercent !== undefined && <MetricRow label="Window used" value={`${usedPercent}%`} />}
      {compactionThreshold !== undefined && compactionThreshold > 0 && (
        <MetricRow
          label="Compacts at"
          value={`${formatTokenCount(compactionThreshold)}${
            compactionSource === 'absolute' ? ' (pinned)' : ''
          }`}
        />
      )}
    </div>
  );
}

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
    return <EmptySection value="token_budget" title="Token Budget" icon={Gauge} />;
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
    // B8 — the room the turn actually had. The four zone thresholds below are
    // instance-wide settings, independent of the model configured: a turn
    // could sit in a « safe » zone whose ceiling exceeded its model's whole
    // window. Absent on payloads persisted before B8.
    context_window,
    context_window_source,
    context_window_model,
    context_used_percent,
    compaction_threshold,
    compaction_threshold_source,
  } = data;
  const progressPercentage =
    thresholds.max > 0 ? Math.min((current_tokens / thresholds.max) * 100, 100) : 0;

  const strategyLabel = strategy ? FALLBACK_STRATEGY_LABELS[strategy] || strategy : null;

  return (
    <DebugSection value="token_budget" title="Token Budget" icon={Gauge} badge={<ZoneBadge zone={zone} />}>
      {/* Catalogue strategy — the PLANNING input this section governs */}
      {strategy && (
        <div className="space-y-1">
          <SubSectionHeader label="Catalogue strategy" />
          <div className="flex items-center gap-2">
            <DebugChip tone={fallbackLevelTone(strategy)}>{strategyLabel}</DebugChip>
            {fallback_active && (
              <span className={cn('text-[10px] italic', TONE_TEXT.warning)}>(degraded mode)</span>
            )}
          </div>
        </div>
      )}

      {/* Current context (for zone calculation) */}
      <div className="space-y-1">
        <SubSectionHeader label="Context size" borderTop={Boolean(strategy)} />
        <MetricRow
          label="Context tokens"
          value={`${formatTokenCount(current_tokens)} / ${formatTokenCount(thresholds.max)}`}
        />
        <MetricRow
          label="Zone"
          value={ZONE_LABELS[zone] || zone}
          valueClassName={cn(TONE_TEXT[zoneTone(zone)], 'font-medium')}
        />
      </div>

      {/* Visual progress bar */}
      <div>
        <SubSectionHeader label="Budget progression" borderTop />
        <div className="relative">
          <div className="h-2 w-full overflow-hidden rounded-full bg-muted">
            <div
              className={cn('h-full transition-all', TONE_BAR[zoneTone(zone)])}
              style={{ width: `${progressPercentage}%` }}
            />
          </div>
          <div className="mt-1 flex justify-between text-[10px] text-muted-foreground">
            <span>0</span>
            <span className={cn('font-medium', TONE_TEXT[zoneTone(zone)])}>
              {Math.round(progressPercentage)}%
            </span>
            <span>{formatTokenCount(thresholds.max)}</span>
          </div>
        </div>
      </div>

      {/* The model's OWN window — the bound that actually truncates, as
          opposed to the instance-wide zones below (ADR-278, B8). */}
      <ModelWindow
        window={context_window}
        source={context_window_source}
        model={context_window_model}
        usedPercent={context_used_percent}
        compactionThreshold={compaction_threshold}
        compactionSource={compaction_threshold_source}
      />

      {/* Zone thresholds */}
      <div>
        <SubSectionHeader label="Zone thresholds" borderTop />
        <div className="grid grid-cols-2 gap-x-4 gap-y-1">
          <MetricRow
            label="Safe"
            value={`< ${formatTokenCount(thresholds.safe)}`}
            valueClassName={TONE_TEXT.success}
          />
          <MetricRow
            label="Warning"
            value={`< ${formatTokenCount(thresholds.warning)}`}
            valueClassName={TONE_TEXT.warning}
          />
          <MetricRow
            label="Critical"
            value={`< ${formatTokenCount(thresholds.critical)}`}
            valueClassName={TONE_TEXT.destructive}
          />
          <MetricRow
            label="Maximum"
            value={formatTokenCount(thresholds.max)}
            valueClassName={TONE_TEXT.destructive}
          />
        </div>
      </div>

      {/* Actual total consumed (v3.1 - includes response) */}
      {total_consumed !== undefined && (
        <div className="space-y-1">
          <SubSectionHeader label="Total consumed (actual)" borderTop />
          <MetricRow
            label="Total"
            value={formatTokenCount(total_consumed)}
            highlight
            valueClassName="text-primary font-bold"
          />
          <div className="grid grid-cols-3 gap-1 text-[10px]">
            <div className="flex flex-col items-center rounded bg-muted/30 p-1">
              <span className="text-muted-foreground">Input</span>
              <span className="font-medium text-foreground">
                {formatTokenCount(tokens_input || 0)}
              </span>
            </div>
            <div className="flex flex-col items-center rounded bg-muted/30 p-1">
              <span className="text-muted-foreground">Output</span>
              <span className="font-medium text-foreground">
                {formatTokenCount(tokens_output || 0)}
              </span>
            </div>
            <div className="flex flex-col items-center rounded bg-muted/30 p-1">
              <span className="text-muted-foreground">Cache</span>
              <span className={cn('font-medium', TONE_TEXT.success)}>
                {formatTokenCount(tokens_cache || 0)}
              </span>
            </div>
          </div>
        </div>
      )}
    </DebugSection>
  );
});
