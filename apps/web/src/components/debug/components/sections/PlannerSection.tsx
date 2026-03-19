/**
 * Planner Intelligence Section Component
 *
 * Displays planner intelligence metrics (optional).
 */

import React from 'react';
import { AccordionItem, AccordionTrigger, AccordionContent } from '@/components/ui/accordion';
import { MetricRow, StrategyBadge } from '../shared';
import { formatTokenCount, formatCost, formatPercent } from '../../utils/formatters';
import type { DebugMetrics } from '@/types/chat';

export interface PlannerSectionProps {
  /** Planner intelligence metrics (can be undefined) */
  data: DebugMetrics['planner_intelligence'];
}

/**
 * Planner Intelligence Section
 *
 * Displays:
 * - Strategy used (template/filtered/generative/panic)
 * - Tokens used, saved, and reduction % vs full catalogue
 * - Plan details (steps count, tools, estimated cost)
 * - Usage flags (template/panic/generative)
 * - Success/error
 *
 * Not displayed if data is undefined (query routed to chat).
 */
export const PlannerSection = React.memo(function PlannerSection({ data }: PlannerSectionProps) {
  if (!data) {
    return null;
  }

  const { strategy, tokens, plan, flags, success, error } = data;

  return (
    <AccordionItem value="planner">
      <AccordionTrigger className="py-2 text-sm">
        <div className="flex items-center">
          <span>Planner Intelligence</span>
          <StrategyBadge strategy={strategy} size="xs" className="ml-2" />
        </div>
      </AccordionTrigger>
      <AccordionContent>
        <div className="space-y-3">
          {/* Status */}
          <div>
            <MetricRow
              label="Success"
              value={success}
              highlight
              valueClassName={success ? 'text-green-700' : 'text-red-700'}
            />
            {error && <MetricRow label="Error" value={error} valueClassName="text-red-700" />}
          </div>

          {/* Strategy */}
          <div className="border-t pt-2">
            <div className="text-xs text-muted-foreground font-medium mb-1.5">Strategy</div>
            <MetricRow label="Selected" value={strategy} highlight />
            <MetricRow label="Used Template" value={flags.used_template} />
            <MetricRow label="Used Panic Mode" value={flags.used_panic_mode} />
            <MetricRow label="Used Generative" value={flags.used_generative} />
          </div>

          {/* Token Economics */}
          <div className="border-t pt-2">
            <div className="text-xs text-muted-foreground font-medium mb-1.5">Token Economics</div>
            <MetricRow label="Tokens Used" value={formatTokenCount(tokens.used)} highlight />
            <MetricRow
              label="Tokens Saved"
              value={formatTokenCount(tokens.saved)}
              valueClassName="text-green-600 font-semibold"
            />
            <MetricRow
              label="Full Catalogue Est."
              value={formatTokenCount(tokens.full_catalogue_estimate)}
              valueClassName="text-muted-foreground"
            />
            <MetricRow
              label="Reduction"
              value={formatPercent(tokens.reduction_percentage / 100)}
              valueClassName="text-green-600 font-semibold"
            />
          </div>

          {/* Plan Details */}
          <div className="border-t pt-2">
            <div className="text-xs text-muted-foreground font-medium mb-1.5">Plan Details</div>
            {plan.steps_count !== undefined && (
              <MetricRow label="Steps Count" value={plan.steps_count} />
            )}
            {plan.tools_used && plan.tools_used.length > 0 && (
              <MetricRow label="Tools Used" value={plan.tools_used.join(', ')} truncate />
            )}
            {plan.estimated_cost_usd !== undefined && plan.estimated_cost_usd !== null && (
              <MetricRow label="Estimated Cost" value={formatCost(plan.estimated_cost_usd)} mono />
            )}
          </div>
        </div>
      </AccordionContent>
    </AccordionItem>
  );
});
