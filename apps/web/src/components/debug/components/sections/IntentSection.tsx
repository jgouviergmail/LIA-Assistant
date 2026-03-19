/**
 * Intent Detection Section Component
 *
 * Displays user intent detection metrics.
 * v3.1: LLM-based analysis via QueryAnalyzerService.
 */

import React from 'react';
import { AccordionItem, AccordionTrigger, AccordionContent } from '@/components/ui/accordion';
import { MetricRow, ThresholdRow, SectionBadge } from '../shared';
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
    <AccordionItem value="intent">
      <AccordionTrigger className="py-2 text-sm">
        <div className="flex items-center gap-2">
          <span>Intent Detection</span>
          {isLLMBased && (
            <span className="text-xs bg-primary/20 text-primary px-1.5 py-0.5 rounded font-medium border border-primary/30">
              LLM
            </span>
          )}
          <SectionBadge passed={passed} value={data.confidence} />
        </div>
      </AccordionTrigger>
      <AccordionContent>
        <div className="space-y-3">
          {/* Main result */}
          <div className="space-y-1">
            <div className="text-xs text-muted-foreground font-medium mb-1">Classification</div>
            <MetricRow label="Action détectée" value={data.detected_intent} highlight />
            <MetricRow label="Confiance" value={data.confidence} highlight />
          </div>

          {/* Objectif utilisateur */}
          <div className="border-t pt-2 space-y-1">
            <div className="text-xs text-muted-foreground font-medium mb-1">Analyse du besoin</div>
            <MetricRow label="Objectif utilisateur" value={data.user_goal} />
            {data.goal_reasoning && (
              <div className="mt-1.5 p-2 bg-muted/30 rounded text-xs text-muted-foreground">
                <span className="font-medium">Raisonnement :</span>{' '}
                <span className="italic">{data.goal_reasoning}</span>
              </div>
            )}
          </div>

          {/* Decision thresholds */}
          {(data.thresholds.high_threshold || data.thresholds.fallback_threshold) && (
            <div className="border-t pt-2">
              <div className="text-xs text-muted-foreground font-medium mb-1.5">
                Seuils de décision
              </div>
              {data.thresholds.high_threshold && (
                <ThresholdRow
                  label="Confiance haute (validation)"
                  check={data.thresholds.high_threshold}
                />
              )}
              {data.thresholds.fallback_threshold && (
                <ThresholdRow
                  label="Seuil de fallback"
                  check={data.thresholds.fallback_threshold}
                />
              )}
            </div>
          )}
        </div>
      </AccordionContent>
    </AccordionItem>
  );
});
