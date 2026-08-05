/**
 * Planner Section Component
 *
 * Displays planner strategy and token-economy metrics (optional).
 */

import React from 'react';
import { ClipboardList } from 'lucide-react';
import { DebugSection, EmptySection, MetricRow, StrategyBadge, SubSectionHeader } from '../shared';
import { formatTokenCount, formatCost, formatPercent } from '../../utils/formatters';
import { TONE_TEXT } from '../../utils/tones';
import type { DebugMetrics } from '@/types/chat';

export interface PlannerSectionProps {
  /** Planner intelligence metrics (can be undefined) */
  data: DebugMetrics['planner_intelligence'];
}

/**
 * Planner Section
 *
 * Displays:
 * - Strategy used (template/filtered/generative/panic)
 * - Tokens used, saved, and reduction % vs full catalogue
 * - Plan details (steps count, tools, estimated cost)
 * - Usage flags (template/panic/generative)
 * - Success/error
 */
export const PlannerSection = React.memo(function PlannerSection({ data }: PlannerSectionProps) {
  if (!data) {
    return (
      <EmptySection
        value="planner"
        title="Planner"
        icon={ClipboardList}
        message="No plan was generated (query routed to chat)."
      />
    );
  }

  const { strategy, tokens, plan, flags, success, error } = data;

  return (
    <DebugSection
      value="planner"
      title="Planner"
      icon={ClipboardList}
      badge={<StrategyBadge strategy={strategy} />}
    >
      {/* Status */}
      <div>
        <MetricRow
          label="Success"
          value={success}
          highlight
          valueClassName={success ? TONE_TEXT.success : TONE_TEXT.destructive}
        />
        {error && <MetricRow label="Error" value={error} valueClassName={TONE_TEXT.destructive} />}
      </div>

      {/* Strategy */}
      <div>
        <SubSectionHeader label="Strategy" borderTop />
        <MetricRow label="Selected" value={strategy} highlight />
        <MetricRow label="Used template" value={flags.used_template} />
        <MetricRow label="Used panic mode" value={flags.used_panic_mode} />
        <MetricRow label="Used generative" value={flags.used_generative} />
      </div>

      {/* Token Economics */}
      <div>
        <SubSectionHeader label="Token economics" borderTop />
        <MetricRow label="Tokens used" value={formatTokenCount(tokens.used)} highlight />
        <MetricRow
          label="Tokens saved"
          value={formatTokenCount(tokens.saved)}
          valueClassName={`${TONE_TEXT.success} font-semibold`}
        />
        <MetricRow
          label="Full catalogue est."
          value={formatTokenCount(tokens.full_catalogue_estimate)}
          valueClassName="text-muted-foreground"
        />
        <MetricRow
          label="Reduction"
          value={formatPercent(tokens.reduction_percentage / 100)}
          valueClassName={`${TONE_TEXT.success} font-semibold`}
        />
      </div>

      {/* Plan Details */}
      <div>
        <SubSectionHeader label="Plan details" borderTop />
        {plan.steps_count !== undefined && <MetricRow label="Steps count" value={plan.steps_count} />}
        {plan.tools_used && plan.tools_used.length > 0 && (
          <MetricRow label="Tools used" value={plan.tools_used.join(', ')} truncate />
        )}
        {plan.estimated_cost_usd !== undefined && plan.estimated_cost_usd !== null && (
          <MetricRow label="Estimated cost" value={formatCost(plan.estimated_cost_usd)} mono />
        )}
      </div>
    </DebugSection>
  );
});
