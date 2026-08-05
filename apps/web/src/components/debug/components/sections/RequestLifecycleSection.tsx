/**
 * Request Lifecycle Section Component (v3.2)
 *
 * Displays execution times per LangGraph node, in true chronological order
 * (the backend orders nodes by their first run-anchored appearance).
 * Token details are available in LLMCallsSection.
 */

import React from 'react';
import { Timer } from 'lucide-react';
import { DebugChip, DebugSection, EmptySection, NodeChip, SubSectionHeader } from '../shared';
import { formatDuration } from '../../utils/formatters';
import { DEBUG_TEXT_SIZES } from '../../utils/constants';
import type { RequestLifecycleMetrics } from '@/types/chat';

export interface RequestLifecycleSectionProps {
  /** Request lifecycle data (may be undefined) */
  data: RequestLifecycleMetrics | undefined;
}

/**
 * Section Execution Times (v3.2)
 *
 * Displays:
 * - Total LLM execution time
 * - Per-node execution time with visual progress bar
 * - Relative time percentage per node
 */
export const RequestLifecycleSection = React.memo(function RequestLifecycleSection({
  data,
}: RequestLifecycleSectionProps) {
  if (!data || data.nodes.length === 0) {
    return (
      <EmptySection
        value="request_lifecycle"
        title="Execution Times"
        icon={Timer}
        message="No LLM call was recorded on this request."
      />
    );
  }

  // Total duration (use provided total or sum)
  const totalDuration =
    data.total_duration_ms ?? data.nodes.reduce((acc, node) => acc + (node.duration_ms || 0), 0);

  // Max duration for progress bar scaling
  const maxNodeDuration = Math.max(...data.nodes.map(n => n.duration_ms || 0), 1);

  return (
    <DebugSection
      value="request_lifecycle"
      title="Execution Times"
      icon={Timer}
      badge={
        totalDuration > 0 ? (
          <DebugChip tone="info">{formatDuration(totalDuration)}</DebugChip>
        ) : undefined
      }
    >
      {/* Total summary */}
      <div className="rounded border border-border/50 bg-muted/30 p-2">
        <div className="flex items-center justify-between">
          <span className="text-xs text-muted-foreground">Total LLM time</span>
          <span className="text-sm font-medium text-primary">{formatDuration(totalDuration)}</span>
        </div>
        <div className="mt-1 text-xs text-muted-foreground">
          {data.total_nodes} node{data.total_nodes > 1 ? 's' : ''} • Sum of all LLM calls
        </div>
      </div>

      {/* Per-node timing */}
      <div>
        <SubSectionHeader label="Node breakdown (chronological)" borderTop />
        <div className="space-y-2">
          {data.nodes.map(node => {
            const duration = node.duration_ms || 0;
            const percentage = totalDuration > 0 ? (duration / totalDuration) * 100 : 0;
            const barWidth = maxNodeDuration > 0 ? (duration / maxNodeDuration) * 100 : 0;

            return (
              <div key={node.name} className="space-y-1">
                <div className="flex items-center gap-2">
                  {/* Node identity chip */}
                  <NodeChip nodeName={node.name} className="min-w-[80px] justify-center" />

                  {/* Duration and percentage */}
                  <div className="flex flex-1 items-center justify-between">
                    <div className={`flex items-center gap-2 ${DEBUG_TEXT_SIZES.small}`}>
                      <span className="font-mono text-primary">{formatDuration(duration)}</span>
                      {node.calls_count > 1 && (
                        <span className="text-muted-foreground">({node.calls_count} calls)</span>
                      )}
                    </div>
                    <span className="text-xs text-muted-foreground">{percentage.toFixed(0)}%</span>
                  </div>
                </div>

                {/* Progress bar - aligned with node chip (min-w-[80px] + gap-2) */}
                <div className="ml-[88px] h-1 overflow-hidden rounded-full bg-muted/50">
                  <div
                    className="h-full rounded-full bg-primary/60 transition-all duration-300"
                    style={{ width: `${barWidth}%` }}
                  />
                </div>
              </div>
            );
          })}
        </div>
      </div>
    </DebugSection>
  );
});
