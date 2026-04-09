/**
 * FOR_EACH Analysis Section Component
 *
 * Displays bulk operation detection metrics (v3.1).
 * Shows when user intent involves iterating over collections.
 */

import React from 'react';
import { AccordionItem, AccordionTrigger, AccordionContent } from '@/components/ui/accordion';
import { EmptySection, MetricRow, SectionBadge } from '../shared';
import {
  CARDINALITY_MODE_LABELS,
  CARDINALITY_ALL_VALUE,
  DEBUG_TEXT_SIZES,
} from '../../utils/constants';
import type { ForEachAnalysis } from '@/types/chat';

export interface ForEachAnalysisSectionProps {
  /** FOR_EACH analysis data (peut etre undefined) */
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
  // Don't render if no data or not detected
  if (!data || !data.detected) {
    return <EmptySection value="for_each_analysis" title="FOR_EACH Analysis" />;
  }

  return (
    <AccordionItem value="for_each_analysis">
      <AccordionTrigger className="py-2 text-sm">
        <div className="flex items-center gap-2">
          <span>FOR_EACH Analysis</span>
          <SectionBadge passed={data.detected} label={data.detected ? 'BULK' : 'N/A'} />
        </div>
      </AccordionTrigger>
      <AccordionContent>
        <div className="space-y-3">
          {/* Detection status */}
          <div className="space-y-1">
            <div className="text-xs text-muted-foreground font-medium mb-1">
              Bulk Operation Detection
            </div>
            <MetricRow
              label="Detected"
              value={data.detected ? 'Yes' : 'No'}
              highlight
              valueClassName={data.detected ? 'text-orange-400 font-semibold' : undefined}
            />
            {data.collection_key && (
              <MetricRow label="Collection" value={data.collection_key} highlight mono />
            )}
          </div>

          {/* Cardinality */}
          <div className="border-t border-border/50 pt-2 space-y-1">
            <div className="text-xs text-muted-foreground font-medium mb-1">Cardinality</div>
            <MetricRow
              label="Mode"
              value={CARDINALITY_MODE_LABELS[data.cardinality_mode] || data.cardinality_mode}
              valueClassName={
                data.cardinality_mode === 'each' || data.cardinality_mode === 'all'
                  ? 'text-orange-400'
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
            <div className="border-t border-border/50 pt-2">
              <div className="text-xs text-muted-foreground font-medium mb-1.5">
                Constraint Hints
              </div>
              <div className="flex flex-wrap gap-1">
                {Object.entries(data.constraint_hints).map(([key, value]) => (
                  <span
                    key={key}
                    className={`${DEBUG_TEXT_SIZES.small} px-1.5 py-0.5 rounded border ${
                      value
                        ? 'bg-primary/20 text-primary border-primary/30'
                        : 'bg-muted text-muted-foreground border-border'
                    }`}
                  >
                    {key.replace('has_', '')}
                  </span>
                ))}
              </div>
            </div>
          )}
        </div>
      </AccordionContent>
    </AccordionItem>
  );
});
