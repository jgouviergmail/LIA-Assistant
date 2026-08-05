/**
 * Execution Timeline Section Component
 *
 * Displays the tool execution timeline (optional).
 */

import React from 'react';
import { ListChecks } from 'lucide-react';
import { ClockIcon } from 'lucide-react';
import { DebugChip, DebugSection, EmptySection, MetricRow, SubSectionHeader } from '../shared';
import { TONE_TEXT, executionStatusTone } from '../../utils/tones';
import { formatDuration } from '../../utils/formatters';
import { cn } from '@/lib/utils';
import type { DebugMetrics } from '@/types/chat';

export interface ExecutionSectionProps {
  /** Execution timeline metrics (can be undefined) */
  data: DebugMetrics['execution_timeline'];
}

/**
 * Section Execution Timeline
 *
 * Displays:
 * - Total number of steps and completed ones
 * - List of steps with status, domain, tool, duration
 * - Overall progress bar
 */
export const ExecutionSection = React.memo(function ExecutionSection({
  data,
}: ExecutionSectionProps) {
  if (!data) {
    return (
      <EmptySection
        value="execution"
        title="Execution Timeline"
        icon={ListChecks}
        message="No plan was executed on this request."
      />
    );
  }

  const { steps = [], total_steps, completed_steps } = data;
  const progressPercentage = total_steps > 0 ? (completed_steps / total_steps) * 100 : 0;

  return (
    <DebugSection
      value="execution"
      title="Execution Timeline"
      icon={ListChecks}
      badge={
        <span className="ml-2 font-mono text-[10px] text-muted-foreground">
          {completed_steps}/{total_steps}
        </span>
      }
    >
      {/* Main metrics */}
      <div>
        <MetricRow label="Total steps" value={total_steps} highlight />
        <MetricRow label="Completed" value={completed_steps} highlight />
      </div>

      {/* Overall progress bar */}
      <div>
        <SubSectionHeader label="Overall progress" borderTop />
        <div className="relative h-2 rounded-full bg-muted">
          <div
            className="absolute left-0 top-0 h-full rounded-full bg-primary transition-all"
            style={{ width: `${progressPercentage}%` }}
          />
        </div>
        <div className="mt-1 flex justify-between text-[10px] text-muted-foreground">
          <span>0%</span>
          <span>{progressPercentage.toFixed(0)}%</span>
          <span>100%</span>
        </div>
      </div>

      {/* Steps timeline */}
      {steps.length > 0 && (
        <div>
          <SubSectionHeader label="Steps" borderTop />
          <div className="space-y-2">
            {steps.map(step => (
              <div key={step.step_id} className="border-l-2 border-border pl-3 pb-1">
                {/* Header: tool + status */}
                <div className="mb-0.5 flex items-center justify-between text-xs">
                  <span className="flex-1 truncate font-mono text-[11px] font-medium">
                    {step.tool_name}
                  </span>
                  <DebugChip tone={executionStatusTone(step.status)} className="ml-2">
                    {step.status}
                  </DebugChip>
                </div>

                {/* Details */}
                <div className="space-y-0.5 text-[10px] text-muted-foreground">
                  <div>Domain: {step.domain}</div>
                  {step.duration_ms !== null && step.duration_ms !== undefined && (
                    <div className="flex items-center gap-1">
                      <ClockIcon className="h-2.5 w-2.5" aria-hidden="true" />
                      {formatDuration(step.duration_ms)}
                    </div>
                  )}
                  {step.success !== undefined && step.success !== null && (
                    <div className={cn(step.success ? TONE_TEXT.success : TONE_TEXT.destructive)}>
                      Success: {step.success ? 'Yes' : 'No'}
                    </div>
                  )}
                </div>
              </div>
            ))}
          </div>
        </div>
      )}
    </DebugSection>
  );
});
