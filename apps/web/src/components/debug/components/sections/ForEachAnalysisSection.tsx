/**
 * FOR_EACH Analysis Section Component
 *
 * Displays bulk operation detection metrics (v3.1).
 * Shows when user intent involves iterating over collections.
 */

import React from 'react';
import { Repeat } from 'lucide-react';
import { DebugChip, DebugSection, EmptySection, MetricRow, SubSectionHeader } from '../shared';
import { CARDINALITY_MODE_LABELS, CARDINALITY_ALL_VALUE } from '../../utils/constants';
import { TONE_TEXT } from '../../utils/tones';
import type { ForEachAnalysis } from '@/types/chat';

export interface ForEachAnalysisSectionProps {
  /** FOR_EACH analysis data (may be undefined) */
  data: ForEachAnalysis | undefined;
}

/**
 * Section FOR_EACH Analysis
 *
 * Displays:
 * - Detection status (detected = bulk operation)
 * - Collection key (contacts, events, etc.)
 * - Cardinality magnitude (number of items)
 * - Cardinality mode (single, multiple, all, each)
 * - Constraint hints (distance, quality, etc.)
 */
export const ForEachAnalysisSection = React.memo(function ForEachAnalysisSection({
  data,
}: ForEachAnalysisSectionProps) {
  if (!data || !data.detected) {
    return (
      <EmptySection
        value="for_each_analysis"
        title="FOR_EACH Analysis"
        icon={Repeat}
        message="No bulk operation detected in this query."
      />
    );
  }

  return (
    <DebugSection
      value="for_each_analysis"
      title="FOR_EACH Analysis"
      icon={Repeat}
      badge={<DebugChip tone="warning">BULK</DebugChip>}
    >
      {/* Detection status */}
      <div className="space-y-1">
        <SubSectionHeader label="Bulk operation detection" />
        <MetricRow
          label="Detected"
          value="Yes"
          highlight
          valueClassName={`${TONE_TEXT.warning} font-semibold`}
        />
        {data.collection_key && (
          <MetricRow label="Collection" value={data.collection_key} highlight mono />
        )}
      </div>

      {/* Cardinality */}
      <div className="space-y-1">
        <SubSectionHeader label="Cardinality" borderTop />
        <MetricRow
          label="Mode"
          value={CARDINALITY_MODE_LABELS[data.cardinality_mode] || data.cardinality_mode}
          valueClassName={
            data.cardinality_mode === 'each' || data.cardinality_mode === 'all'
              ? TONE_TEXT.warning
              : undefined
          }
        />
        {data.cardinality_magnitude !== null && (
          <MetricRow
            label="Magnitude"
            value={
              data.cardinality_magnitude === CARDINALITY_ALL_VALUE
                ? 'All'
                : String(data.cardinality_magnitude)
            }
            mono
          />
        )}
      </div>

      {/* Constraint hints */}
      {Object.keys(data.constraint_hints).length > 0 && (
        <div>
          <SubSectionHeader label="Constraint hints" borderTop />
          <div className="flex flex-wrap gap-1">
            {Object.entries(data.constraint_hints).map(([key, value]) => (
              <DebugChip key={key} tone={value ? 'info' : 'neutral'}>
                {key.replace('has_', '')}
              </DebugChip>
            ))}
          </div>
        </div>
      )}
    </DebugSection>
  );
});
