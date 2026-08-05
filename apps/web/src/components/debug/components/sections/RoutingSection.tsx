/**
 * Routing Decision Section Component
 *
 * Displays the routing decision: chat (conversation) vs planner (tools).
 */

import React from 'react';
import { Route } from 'lucide-react';
import {
  DebugSection,
  InfoRow,
  MetricRow,
  SectionBadge,
  SubSectionHeader,
  ThresholdRow,
} from '../shared';
import { DEFAULT_THRESHOLDS } from '../../utils/constants';
import { nodeChipClasses } from '../../utils/tones';
import { cn } from '@/lib/utils';
import type { DebugMetrics } from '@/types/chat';

export interface RoutingSectionProps {
  /** Routing decision metrics */
  data: DebugMetrics['routing_decision'];
}

/**
 * Routing Decision Section
 *
 * Clearly displays:
 * - The chosen destination (chat = conversation, planner = tools)
 * - The decision confidence level
 * - Whether the LLM was bypassed (optimization)
 * - The reasoning that led to this choice
 */
export const RoutingSection = React.memo(function RoutingSection({ data }: RoutingSectionProps) {
  const minConfidence =
    data.thresholds.min_confidence?.value ?? DEFAULT_THRESHOLDS.routing.min_confidence;
  const passed = data.confidence >= minConfidence;
  const isPlanner = data.route_to === 'planner';

  return (
    <DebugSection
      value="routing"
      title="Routing Decision"
      icon={Route}
      badge={<SectionBadge passed={passed} value={data.confidence} />}
    >
      {/* Routing decision */}
      <div className="space-y-1">
        <SubSectionHeader label="Destination" />
        <MetricRow
          label="Routed to"
          value={isPlanner ? 'Planner (tools)' : 'Chat (conversation)'}
          highlight
          valueClassName={cn(
            'inline-flex rounded-full border px-1.5 font-medium',
            nodeChipClasses(isPlanner ? 'planner' : 'response')
          )}
        />
        <MetricRow label="Confidence" value={data.confidence} highlight />
        <MetricRow label="LLM bypassed" value={data.bypass_llm ? 'Yes (rules)' : 'No'} />
      </div>

      {/* Reasoning */}
      {(data.reasoning_trace ?? []).length > 0 && (
        <div>
          <SubSectionHeader label="Reasoning" borderTop />
          <div className="rounded bg-muted/30 p-2 text-xs text-muted-foreground">
            {(data.reasoning_trace ?? []).map((step, i) => (
              <span key={i}>
                {i > 0 && <span className="mx-1 text-muted-foreground">→</span>}
                <span>{step}</span>
              </span>
            ))}
          </div>
        </div>
      )}

      {/* Decision thresholds */}
      <div>
        <SubSectionHeader label="Decision thresholds" borderTop />
        {data.thresholds.chat_semantic_threshold && (
          <ThresholdRow label="Chat threshold (low)" check={data.thresholds.chat_semantic_threshold} />
        )}
        {data.thresholds.high_semantic_threshold && (
          <ThresholdRow
            label="Planner threshold (high)"
            check={data.thresholds.high_semantic_threshold}
          />
        )}
        {data.thresholds.min_confidence && (
          <ThresholdRow label="Minimum confidence" check={data.thresholds.min_confidence} />
        )}
        {data.thresholds.chat_override_threshold && (
          <InfoRow label="Chat override" check={data.thresholds.chat_override_threshold} />
        )}
      </div>
    </DebugSection>
  );
});
