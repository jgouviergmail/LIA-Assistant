/**
 * Request Lifecycle Section Component (v3.2)
 *
 * Displays execution times per LangGraph node.
 * Focuses on timing metrics (duration) with visual progress bars.
 * Token details are available in LLMCallsSection.
 */

import React from 'react';
import { AccordionItem, AccordionTrigger, AccordionContent } from '@/components/ui/accordion';
import { formatDuration } from '../../utils/formatters';
import { getNodeColor, DEBUG_TEXT_SIZES, DEBUG_WIDTHS } from '../../utils/constants';
import { cn } from '@/lib/utils';
import type { RequestLifecycleMetrics } from '@/types/chat';

export interface RequestLifecycleSectionProps {
  /** Request lifecycle data (peut etre undefined) */
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
    return null;
  }

  // Calculate total duration (use provided total or sum)
  const totalDuration =
    data.total_duration_ms ?? data.nodes.reduce((acc, node) => acc + (node.duration_ms || 0), 0);

  // Find max duration for progress bar scaling
  const maxNodeDuration = Math.max(...data.nodes.map(n => n.duration_ms || 0), 1);

  return (
    <AccordionItem value="request_lifecycle">
      <AccordionTrigger className="py-2 text-sm">
        <div className="flex items-center gap-2">
          <span>Execution Times</span>
          {totalDuration > 0 && (
            <span className="text-xs bg-blue-500/20 text-blue-400 px-2 py-0.5 rounded border border-blue-500/30">
              {formatDuration(totalDuration)}
            </span>
          )}
        </div>
      </AccordionTrigger>
      <AccordionContent>
        <div className="space-y-3">
          {/* Total summary */}
          <div className="p-2 bg-muted/30 rounded border border-border/50">
            <div className="flex justify-between items-center">
              <span className="text-xs text-muted-foreground">Total LLM Time</span>
              <span className="text-sm font-medium text-blue-400">
                {formatDuration(totalDuration)}
              </span>
            </div>
            <div className="text-xs text-muted-foreground mt-1">
              {data.total_nodes} node{data.total_nodes > 1 ? 's' : ''} • Sum of all LLM calls
            </div>
          </div>

          {/* Per-node timing */}
          <div className="border-t border-border/50 pt-2">
            <div className="text-xs text-muted-foreground font-medium mb-2">Node Breakdown</div>
            <div className="space-y-2">
              {data.nodes.map(node => {
                const duration = node.duration_ms || 0;
                const percentage = totalDuration > 0 ? (duration / totalDuration) * 100 : 0;
                const barWidth = maxNodeDuration > 0 ? (duration / maxNodeDuration) * 100 : 0;

                return (
                  <div key={node.name} className="space-y-1">
                    <div className="flex items-center gap-2">
                      {/* Node name badge */}
                      <div
                        className={cn(
                          'flex items-center justify-center px-2 py-1 rounded border font-medium',
                          DEBUG_TEXT_SIZES.small,
                          DEBUG_WIDTHS.nodeBadge,
                          getNodeColor(node.name)
                        )}
                      >
                        {node.name}
                      </div>

                      {/* Duration and percentage */}
                      <div className="flex-1 flex items-center justify-between">
                        <div className={cn('flex items-center gap-2', DEBUG_TEXT_SIZES.small)}>
                          <span className="font-mono text-blue-400">
                            {formatDuration(duration)}
                          </span>
                          {node.calls_count > 1 && (
                            <span className="text-muted-foreground">
                              ({node.calls_count} calls)
                            </span>
                          )}
                        </div>
                        <span className="text-xs text-muted-foreground">
                          {percentage.toFixed(0)}%
                        </span>
                      </div>
                    </div>

                    {/* Progress bar - aligned with node badge (min-w-[80px] + gap-2) */}
                    <div className="ml-[88px] h-1 bg-muted/50 rounded-full overflow-hidden">
                      <div
                        className="h-full bg-blue-500/60 rounded-full transition-all duration-300"
                        style={{ width: `${barWidth}%` }}
                      />
                    </div>
                  </div>
                );
              })}
            </div>
          </div>
        </div>
      </AccordionContent>
    </AccordionItem>
  );
});
