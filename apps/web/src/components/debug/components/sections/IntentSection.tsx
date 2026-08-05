/**
 * Intent Detection Section Component
 *
 * Displays user intent detection metrics.
 * v3.1: LLM-based analysis via QueryAnalyzerService.
 */

import React from 'react';
import { Target } from 'lucide-react';
import {
  DebugChip,
  DebugSection,
  MetricRow,
  SectionBadge,
  SubSectionHeader,
  ThresholdRow,
} from '../shared';
import { DEFAULT_THRESHOLDS } from '../../utils/constants';
import type { DebugMetrics, IntelligentMechanisms } from '@/types/chat';

export interface IntentSectionProps {
  /** Intent detection metrics */
  data: DebugMetrics['intent_detection'];
  /** v3.1: Intelligent mechanisms (for LLM badge) */
  mechanisms?: IntelligentMechanisms;
}

/**
 * Intent Detection Section
 *
 * Clearly displays:
 * - The detected technical intent (search, create, etc.)
 * - The detection confidence level
 * - The inferred user goal
 * - The reasoning justifying the classification
 */
export const IntentSection = React.memo(function IntentSection({
  data,
  mechanisms,
}: IntentSectionProps) {
  const highThreshold = data.thresholds.high_threshold?.value ?? DEFAULT_THRESHOLDS.intent.high;
  const passed = data.confidence >= highThreshold;
  const isLLMBased = mechanisms?.llm_query_analysis?.applied ?? false;

  return (
    <DebugSection
      value="intent"
      title="Intent Detection"
      icon={Target}
      badge={
        <>
          {isLLMBased && <DebugChip tone="info">LLM</DebugChip>}
          <SectionBadge passed={passed} value={data.confidence} />
        </>
      }
    >
      {/* Main result */}
      <div className="space-y-1">
        <SubSectionHeader label="Classification" />
        <MetricRow label="Detected action" value={data.detected_intent} highlight />
        <MetricRow label="Confidence" value={data.confidence} highlight />
      </div>

      {/* User goal */}
      <div className="space-y-1">
        <SubSectionHeader label="Need analysis" borderTop />
        <MetricRow label="User goal" value={data.user_goal} />
        {data.goal_reasoning && (
          <div className="mt-1.5 rounded bg-muted/30 p-2 text-xs text-muted-foreground">
            <span className="font-medium">Reasoning:</span>{' '}
            <span className="italic">{data.goal_reasoning}</span>
          </div>
        )}
      </div>

      {/* Decision thresholds */}
      {(data.thresholds.high_threshold || data.thresholds.fallback_threshold) && (
        <div>
          <SubSectionHeader label="Decision thresholds" borderTop />
          {data.thresholds.high_threshold && (
            <ThresholdRow
              label="High confidence (validation)"
              check={data.thresholds.high_threshold}
            />
          )}
          {data.thresholds.fallback_threshold && (
            <ThresholdRow label="Fallback threshold" check={data.thresholds.fallback_threshold} />
          )}
        </div>
      )}
    </DebugSection>
  );
});
