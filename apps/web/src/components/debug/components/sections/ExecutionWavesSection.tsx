/**
 * Execution Waves Section Component
 *
 * Visualizes PLANNED parallel execution waves (v3.1): how the plan's steps
 * are grouped for parallel execution. Shown before the actual timeline in
 * the execution-ordered reading (planned → actual).
 */

import React from 'react';
import { Waves } from 'lucide-react';
import { DebugChip, DebugSection, EmptySection, MetricRow, SubSectionHeader } from '../shared';
import { formatPercent } from '../../utils/formatters';
import { TONE_TEXT } from '../../utils/tones';
import { DEBUG_TEXT_SIZES, DEBUG_WIDTHS } from '../../utils/constants';
import type { ExecutionWavesInfo } from '@/types/chat';

export interface ExecutionWavesSectionProps {
  /** Execution waves data (may be undefined) */
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
    return (
      <EmptySection
        value="execution_waves"
        title="Execution Waves"
        icon={Waves}
        message="No multi-step plan to parallelize on this request."
      />
    );
  }

  // Parallelism efficiency (avg vs max possible)
  const parallelismEfficiency =
    data.max_parallelism > 0 ? data.average_parallelism / data.max_parallelism : 0;

  return (
    <DebugSection
      value="execution_waves"
      title="Execution Waves"
      icon={Waves}
      badge={
        <DebugChip tone="neutral">
          {data.total_waves} wave{data.total_waves > 1 ? 's' : ''}
        </DebugChip>
      }
    >
      {/* Summary metrics */}
      <div className="space-y-1">
        <SubSectionHeader label="Planned parallelism" />
        <MetricRow label="Total waves" value={data.total_waves} highlight />
        <MetricRow
          label="Max parallelism"
          value={data.max_parallelism}
          highlight
          valueClassName="text-primary font-semibold"
        />
        <MetricRow label="Critical path" value={`${data.critical_path_length} steps`} />
        <MetricRow label="Avg parallelism" value={data.average_parallelism.toFixed(2)} />
        <MetricRow
          label="Efficiency"
          value={formatPercent(parallelismEfficiency)}
          valueClassName={
            parallelismEfficiency >= 0.7
              ? TONE_TEXT.success
              : parallelismEfficiency >= 0.4
                ? TONE_TEXT.warning
                : TONE_TEXT.destructive
          }
        />
      </div>

      {/* Wave visualization */}
      {data.waves.length > 0 && (
        <div>
          <SubSectionHeader label="Wave breakdown" borderTop />
          <div className="space-y-2">
            {data.waves.map(wave => (
              <div key={wave.wave_id} className="space-y-1">
                <div className="flex items-center gap-2">
                  <span
                    className={`${DEBUG_TEXT_SIZES.small} text-muted-foreground ${DEBUG_WIDTHS.waveLabel}`}
                  >
                    Wave {wave.wave_id + 1}
                  </span>
                  <div className="h-2 flex-1 overflow-hidden rounded-full bg-muted">
                    <div
                      className="h-full rounded-full bg-primary"
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
                      className={`${DEBUG_TEXT_SIZES.tiny} rounded border border-border bg-muted px-1 py-0.5 font-mono`}
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
    </DebugSection>
  );
});
