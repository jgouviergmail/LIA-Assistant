/**
 * Tool Selection Section Component
 *
 * Displays the tools selected to execute the query.
 * Handles the case where the query routes to chat (no tools).
 *
 * v3.1 LLM-based: The planner selects tools directly.
 */

import React from 'react';
import { Wrench } from 'lucide-react';
import { validateToolScores } from '../../validation/validators';
import {
  DebugSection,
  EmptySection,
  InfoRow,
  MetricRow,
  ScoresList,
  SectionBadge,
  SubSectionHeader,
  ThresholdRow,
  ToolMatchRow,
} from '../shared';
import { DEFAULT_THRESHOLDS } from '../../utils/constants';
import { TONE_TEXT } from '../../utils/tones';
import { formatPercent } from '../../utils/formatters';
import type { DebugMetrics } from '@/types/chat';

export interface ToolSectionProps {
  /** Tool selection metrics (can be undefined if chat) */
  data: DebugMetrics['tool_selection'];
}

/**
 * Section Tool Selection
 *
 * v3.1 LLM-based:
 * - The planner selects tools via LLM
 * - Direct confidence scores (no more softmax/calibration)
 */
export const ToolSection = React.memo(function ToolSection({ data }: ToolSectionProps) {
  // Case: no selection (routed to chat)
  if (!data) {
    return (
      <EmptySection
        value="tools"
        title="Tool Selection"
        icon={Wrench}
        message="Routed to chat (simple conversation) — no tool selection ran."
      />
    );
  }

  const scoresValidation = validateToolScores(data);
  const primaryMin = data.thresholds.primary_min?.value ?? DEFAULT_THRESHOLDS.tool.primary_min;
  const passed = data.top_score >= primaryMin;

  return (
    <DebugSection
      value="tools"
      title="Tool Selection"
      icon={Wrench}
      badge={<SectionBadge passed={passed} value={data.top_score} />}
    >
      {/* Selection summary */}
      <div className="space-y-1">
        <SubSectionHeader label="Selection outcome" />
        <MetricRow label="Tools selected" value={(data.selected_tools ?? []).length} highlight />
        <MetricRow
          label="Confidence"
          value={formatPercent(data.top_score)}
          highlight
          valueClassName={passed ? `${TONE_TEXT.success} font-semibold` : TONE_TEXT.destructive}
        />
        <MetricRow label="Uncertainty" value={data.has_uncertainty ? 'Yes' : 'No'} />
      </div>

      {/* Detailed tools list */}
      {(data.selected_tools ?? []).length > 0 && (
        <div>
          <SubSectionHeader label="Selected tools" borderTop />
          <div className="space-y-1">
            {(data.selected_tools ?? []).map((tool, index) => (
              <ToolMatchRow key={`${tool.tool_name}-${index}`} tool={tool} />
            ))}
          </div>
        </div>
      )}

      {/* Configuration */}
      <div>
        <SubSectionHeader label="Thresholds" borderTop />
        {data.thresholds.primary_min && (
          <ThresholdRow label="Minimum confidence" check={data.thresholds.primary_min} />
        )}
        {data.thresholds.max_tools && (
          <InfoRow label="Maximum tools" check={data.thresholds.max_tools} />
        )}
      </div>

      {/* Score details */}
      {scoresValidation.success && (
        <div className="border-t border-border/50 pt-2">
          <ScoresList
            scores={scoresValidation.data!}
            label="Confidence per tool"
            passThreshold={primaryMin}
          />
        </div>
      )}

      {/* Error if no scores */}
      {!scoresValidation.success && scoresValidation.errors?.[0] !== 'SECTION_ABSENT' && (
        <div className="rounded border border-destructive/30 bg-destructive/10 p-2 text-xs text-destructive">
          <strong>Error:</strong> {scoresValidation.errors?.[0] || 'No scores available'}
        </div>
      )}
    </DebugSection>
  );
});
