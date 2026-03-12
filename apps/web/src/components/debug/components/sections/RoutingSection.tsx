/**
 * Routing Decision Section Component
 *
 * Displays the routing decision: chat (conversation) vs planner (tools).
 */

import React from 'react';
import {
  MetricRow,
  ThresholdRow,
  InfoRow,
  SectionBadge,
  DebugSection,
} from '../shared';
import { DEFAULT_THRESHOLDS } from '../../utils/constants';
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
export const RoutingSection = React.memo(function RoutingSection({
  data,
}: RoutingSectionProps) {
  const minConfidence = data.thresholds.min_confidence?.value ?? DEFAULT_THRESHOLDS.routing.min_confidence;
  const passed = data.confidence >= minConfidence;
  const isPlanner = data.route_to === 'planner';

  return (
    <DebugSection
      value="routing"
      title="Routing Decision"
      badge={<SectionBadge passed={passed} value={data.confidence} />}
    >
          {/* Routing decision */}
          <div className="space-y-1">
            <div className="text-xs text-muted-foreground font-medium mb-1">
              Destination
            </div>
            <MetricRow
              label="Route vers"
              value={isPlanner ? 'Planner (outils)' : 'Chat (conversation)'}
              highlight
              valueClassName={isPlanner ? 'text-blue-400 font-bold' : 'text-purple-400 font-bold'}
            />
            <MetricRow
              label="Confiance"
              value={data.confidence}
              highlight
            />
            <MetricRow
              label="LLM bypassé"
              value={data.bypass_llm ? 'Oui (règles)' : 'Non'}
            />
          </div>

          {/* Raisonnement */}
          {(data.reasoning_trace ?? []).length > 0 && (
            <div className="border-t pt-2">
              <div className="text-xs text-muted-foreground font-medium mb-1">
                Raisonnement
              </div>
              <div className="p-2 bg-muted/30 rounded text-xs text-muted-foreground">
                {(data.reasoning_trace ?? []).map((step, i) => (
                  <span key={i}>
                    {i > 0 && <span className="mx-1 text-muted-foreground/50">→</span>}
                    <span>{step}</span>
                  </span>
                ))}
              </div>
            </div>
          )}

          {/* Decision thresholds */}
          <div className="border-t pt-2">
            <div className="text-xs text-muted-foreground font-medium mb-1.5">
              Seuils de décision
            </div>
            {data.thresholds.chat_semantic_threshold && (
              <ThresholdRow
                label="Seuil chat (bas)"
                check={data.thresholds.chat_semantic_threshold}
              />
            )}
            {data.thresholds.high_semantic_threshold && (
              <ThresholdRow
                label="Seuil planner (haut)"
                check={data.thresholds.high_semantic_threshold}
              />
            )}
            {data.thresholds.min_confidence && (
              <ThresholdRow
                label="Confiance minimum"
                check={data.thresholds.min_confidence}
              />
            )}
            {data.thresholds.chat_override_threshold && (
              <InfoRow
                label="Override chat"
                check={data.thresholds.chat_override_threshold}
              />
            )}
          </div>
    </DebugSection>
  );
});
