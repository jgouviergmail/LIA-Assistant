/**
 * Execution Waves Section Component
 *
 * Visualizes parallel execution waves (v3.1).
 * Shows how steps are grouped for parallel execution.
 */

import React from 'react';
import { AccordionItem, AccordionTrigger, AccordionContent } from '@/components/ui/accordion';
import { MetricRow } from '../shared';
import { formatPercent } from '../../utils/formatters';
import { DEBUG_TEXT_SIZES, DEBUG_WIDTHS } from '../../utils/constants';
import type { ExecutionWavesInfo } from '@/types/chat';

export interface ExecutionWavesSectionProps {
  /** Execution waves data (peut etre undefined) */
  data: ExecutionWavesInfo | undefined;
}

/**
 * Section Execution Waves
 *
 * Displays:
 * - Total number of waves
 * - Maximum parallelism achieved
 * - Critical path length
 * - Average parallelism
 * - Visual wave breakdown with steps
 */
export const ExecutionWavesSection = React.memo(function ExecutionWavesSection({
  data,
}: ExecutionWavesSectionProps) {
  if (!data || data.total_waves === 0) {
    return null;
  }

  // Calculate parallelism efficiency (avg vs max possible)
  const parallelismEfficiency =
    data.max_parallelism > 0 ? data.average_parallelism / data.max_parallelism : 0;

  return (
    <AccordionItem value="execution_waves">
      <AccordionTrigger className="py-2 text-sm">
        <div className="flex items-center gap-2">
          <span>Execution Waves</span>
          <span className="text-xs bg-muted text-muted-foreground px-2 py-0.5 rounded border border-border">
            {data.total_waves} wave{data.total_waves > 1 ? 's' : ''}
          </span>
        </div>
      </AccordionTrigger>
      <AccordionContent>
        <div className="space-y-3">
          {/* Summary metrics */}
          <div className="space-y-1">
            <div className="text-xs text-muted-foreground font-medium mb-1">
              Parallelism Metrics
            </div>
            <MetricRow label="Total Waves" value={data.total_waves} highlight />
            <MetricRow
              label="Max Parallelism"
              value={data.max_parallelism}
              highlight
              valueClassName="text-blue-400 font-semibold"
            />
            <MetricRow label="Critical Path" value={`${data.critical_path_length} steps`} />
            <MetricRow label="Avg Parallelism" value={data.average_parallelism.toFixed(2)} />
            <MetricRow
              label="Efficiency"
              value={formatPercent(parallelismEfficiency)}
              valueClassName={
                parallelismEfficiency >= 0.7
                  ? 'text-green-400'
                  : parallelismEfficiency >= 0.4
                    ? 'text-yellow-400'
                    : 'text-red-400'
              }
            />
          </div>

          {/* Wave visualization */}
          {data.waves.length > 0 && (
            <div className="border-t border-border/50 pt-2">
              <div className="text-xs text-muted-foreground font-medium mb-2">Wave Breakdown</div>
              <div className="space-y-2">
                {data.waves.map(wave => (
                  <div key={wave.wave_id} className="space-y-1">
                    <div className="flex items-center gap-2">
                      <span
                        className={`${DEBUG_TEXT_SIZES.small} text-muted-foreground ${DEBUG_WIDTHS.waveLabel}`}
                      >
                        Wave {wave.wave_id + 1}
                      </span>
                      <div className="flex-1 h-2 bg-muted rounded-full overflow-hidden">
                        <div
                          className="h-full bg-blue-500 rounded-full"
                          style={{
                            width: `${(wave.size / data.max_parallelism) * 100}%`,
                          }}
                        />
                      </div>
                      <span
                        className={`${DEBUG_TEXT_SIZES.small} text-muted-foreground ${DEBUG_WIDTHS.waveCount} text-right`}
                      >
                        {wave.size}
                      </span>
                    </div>
                    <div className="flex flex-wrap gap-1 pl-14">
                      {wave.steps.map(stepId => (
                        <span
                          key={stepId}
                          className={`${DEBUG_TEXT_SIZES.tiny} px-1 py-0.5 bg-muted rounded border border-border font-mono`}
                        >
                          {stepId}
                        </span>
                      ))}
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
      </AccordionContent>
    </AccordionItem>
  );
});
