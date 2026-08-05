/**
 * Domain Selection Section Component
 *
 * Displays the functional domains identified for the query.
 * v3.1: LLM-based selection via QueryAnalyzerService.
 */

import React from 'react';
import { Layers } from 'lucide-react';
import { validateDomainScores } from '../../validation/validators';
import {
  DebugChip,
  DebugSection,
  InfoRow,
  MetricRow,
  ScoresList,
  SectionBadge,
  SubSectionHeader,
  ThresholdRow,
} from '../shared';
import { DEFAULT_THRESHOLDS } from '../../utils/constants';
import { TONE_TEXT } from '../../utils/tones';
import { formatPercent } from '../../utils/formatters';
import type { DebugMetrics, IntelligentMechanisms } from '@/types/chat';

export interface DomainSectionProps {
  /** Domain selection metrics */
  data: DebugMetrics['domain_selection'];
  /** v3.1: Intelligent mechanisms (for LLM badge) */
  mechanisms?: IntelligentMechanisms;
}

/**
 * Section Domain Selection
 *
 * Architecture v3.1 LLM-based:
 * - The LLM analyzes the query and selects relevant domains
 * - A single confidence score is assigned to all selected domains
 */
export const DomainSection = React.memo(function DomainSection({
  data,
  mechanisms,
}: DomainSectionProps) {
  const scoresValidation = validateDomainScores(data);
  const primaryMin = data.thresholds.primary_min?.value ?? DEFAULT_THRESHOLDS.domain.primary_min;
  const passed = data.top_score >= primaryMin;
  const isLLMBased = mechanisms?.llm_query_analysis?.applied ?? false;
  const llmReasoning = mechanisms?.llm_query_analysis?.reasoning;

  return (
    <DebugSection
      value="domain"
      title="Domain Selection"
      icon={Layers}
      badge={
        <>
          {isLLMBased && <DebugChip tone="info">LLM</DebugChip>}
          <SectionBadge passed={passed} value={data.top_score} />
        </>
      }
    >
      {/* Selected domains */}
      <div className="space-y-1">
        <SubSectionHeader label="Selection outcome" />
        <MetricRow
          label="Active domains"
          value={data.selected_domains.join(', ') || 'None'}
          highlight
        />
        <MetricRow label="Primary domain" value={data.primary_domain} highlight />
        <MetricRow
          label="LLM confidence"
          value={formatPercent(data.top_score)}
          highlight
          valueClassName={passed ? `${TONE_TEXT.success} font-semibold` : TONE_TEXT.destructive}
        />
      </div>

      {/* LLM reasoning (if available) */}
      {llmReasoning && (
        <div>
          <SubSectionHeader label="LLM reasoning" borderTop />
          <div className="rounded border border-border/50 bg-muted/30 p-2 text-xs italic text-foreground/80">
            {llmReasoning}
          </div>
        </div>
      )}

      {/* Configuration */}
      <div>
        <SubSectionHeader label="Thresholds" borderTop />
        {data.thresholds.primary_min && (
          <ThresholdRow label="Minimum confidence" check={data.thresholds.primary_min} />
        )}
        {data.thresholds.max_domains && (
          <InfoRow label="Maximum domains" check={data.thresholds.max_domains} />
        )}
      </div>

      {/* Score details per domain */}
      <div className="border-t border-border/50 pt-2">
        {scoresValidation.success ? (
          <ScoresList
            scores={scoresValidation.data!}
            label="Confidence per domain"
            passThreshold={primaryMin}
            selectedItems={data.selected_domains}
          />
        ) : (
          <div className="rounded border border-destructive/30 bg-destructive/10 p-2 text-xs text-destructive">
            <strong>Error:</strong> {scoresValidation.errors?.[0] || 'No scores available'}
          </div>
        )}
      </div>
    </DebugSection>
  );
});
