/**
 * ReAct Execution Section Component (v3.4, ADR-070)
 *
 * The autonomous loop of the turn: iterations against the PUBLISHED bound
 * (ADR-184: an enforced limit travels with the value it constrains), wall
 * time, and the tool roster the loop could draw from.
 */

import React from 'react';
import { Repeat2 } from 'lucide-react';
import { DebugChip, DebugSection, MetricRow, SubSectionHeader } from '../shared';
import { TONE_BAR, TONE_TEXT } from '../../utils/tones';
import { cn } from '@/lib/utils';
import type { ReactExecutionMetrics } from '@/types/chat';

export interface ReactExecutionSectionProps {
  data: ReactExecutionMetrics | undefined;
}

export const ReactExecutionSection = React.memo(function ReactExecutionSection({
  data,
}: ReactExecutionSectionProps) {
  // Absent entirely in pipeline mode: the orchestrator only mounts this
  // section when the turn ran in ReAct mode.
  if (!data) return null;

  const atCeiling = data.max_iterations > 0 && data.iterations >= data.max_iterations;
  const ratio = data.max_iterations > 0 ? Math.min(data.iterations / data.max_iterations, 1) : 0;

  return (
    <DebugSection
      value="react_execution"
      title="ReAct Loop"
      icon={Repeat2}
      anomaly={atCeiling}
      badge={
        <DebugChip tone={atCeiling ? 'warning' : 'info'}>
          {data.iterations}/{data.max_iterations}
        </DebugChip>
      }
    >
      {/* Loop metrics */}
      <div className="space-y-1">
        <SubSectionHeader label="Loop" />
        <MetricRow label="Iterations" value={`${data.iterations}/${data.max_iterations}`} highlight />
        <MetricRow label="Elapsed" value={`${data.elapsed_seconds.toFixed(1)}s`} mono />
        <MetricRow label="Tool calls executed" value={data.executed_tool_calls} />
      </div>

      {/* Iteration budget bar */}
      <div>
        <div className="h-1.5 w-full overflow-hidden rounded-full bg-muted/50">
          <div
            className={cn('h-full rounded-full', atCeiling ? TONE_BAR.warning : TONE_BAR.info)}
            style={{ width: `${ratio * 100}%` }}
          />
        </div>
        {atCeiling && (
          <div className={cn('mt-1 text-[10px]', TONE_TEXT.warning)}>
            The loop hit its iteration ceiling — the answer may be a forced finalization.
          </div>
        )}
      </div>

      {/* Tool roster */}
      {data.tool_names.length > 0 && (
        <div>
          <SubSectionHeader label={`Available tools (${data.tool_names.length})`} borderTop />
          <div className="flex flex-wrap gap-1">
            {data.tool_names.map(name => (
              <span
                key={name}
                className="rounded border border-border bg-muted px-1.5 py-0.5 font-mono text-[10px]"
              >
                {name}
              </span>
            ))}
          </div>
        </div>
      )}
    </DebugSection>
  );
});
