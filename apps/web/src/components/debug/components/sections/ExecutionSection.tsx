/**
 * Execution Timeline Section Component
 *
 * Displays the tool execution timeline (optional).
 */

import React from 'react';
import {
  AccordionItem,
  AccordionTrigger,
  AccordionContent,
} from '@/components/ui/accordion';
import { MetricRow } from '../shared';
import { EXECUTION_STATUS_COLORS } from '../../utils/constants';
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
 * - Progress bars per step
 *
 * Not displayed if data is undefined (no tool execution).
 */
export const ExecutionSection = React.memo(function ExecutionSection({
  data,
}: ExecutionSectionProps) {
  if (!data) {
    return null;
  }

  const { steps = [], total_steps, completed_steps } = data;
  const progressPercentage =
    total_steps > 0 ? (completed_steps / total_steps) * 100 : 0;

  return (
    <AccordionItem value="execution">
      <AccordionTrigger className="py-2 text-sm">
        <div className="flex items-center">
          <span>Execution Timeline</span>
          <span className="ml-2 text-[10px] font-mono text-muted-foreground">
            {completed_steps}/{total_steps}
          </span>
        </div>
      </AccordionTrigger>
      <AccordionContent>
        <div className="space-y-3">
          {/* Main metrics */}
          <div>
            <MetricRow label="Total Steps" value={total_steps} highlight />
            <MetricRow label="Completed" value={completed_steps} highlight />
          </div>

          {/* Overall progress bar */}
          <div className="border-t pt-2">
            <div className="text-xs text-muted-foreground font-medium mb-2">
              Overall Progress
            </div>
            <div className="relative h-2 bg-gray-200 rounded-full">
              <div
                className="absolute left-0 top-0 h-full bg-blue-500 rounded-full transition-all"
                style={{ width: `${progressPercentage}%` }}
              />
            </div>
            <div className="flex justify-between mt-1 text-[10px] text-muted-foreground">
              <span>0%</span>
              <span>{progressPercentage.toFixed(0)}%</span>
              <span>100%</span>
            </div>
          </div>

          {/* Steps timeline */}
          {steps.length > 0 && (
            <div className="border-t pt-2">
              <div className="text-xs text-muted-foreground font-medium mb-2">
                Steps Timeline
              </div>
              <div className="space-y-2">
                {steps.map((step) => {
                  const statusColorClass = EXECUTION_STATUS_COLORS[step.status];

                  return (
                    <div
                      key={step.step_id}
                      className="border-l-2 border-gray-300 pl-3 pb-1"
                    >
                      {/* Header: tool + status */}
                      <div className="flex items-center justify-between text-xs mb-0.5">
                        <span className="font-mono text-[11px] font-medium truncate flex-1">
                          {step.tool_name}
                        </span>
                        <span
                          className={cn(
                            'text-[10px] px-1.5 py-0.5 rounded uppercase font-medium ml-2',
                            statusColorClass
                          )}
                        >
                          {step.status}
                        </span>
                      </div>

                      {/* Details */}
                      <div className="text-[10px] text-muted-foreground space-y-0.5">
                        <div>Domain: {step.domain}</div>
                        {step.duration_ms !== null && step.duration_ms !== undefined && (
                          <div>Duration: {formatDuration(step.duration_ms)}</div>
                        )}
                        {step.success !== undefined && step.success !== null && (
                          <div
                            className={
                              step.success ? 'text-green-600' : 'text-red-600'
                            }
                          >
                            Success: {step.success ? 'Yes' : 'No'}
                          </div>
                        )}
                      </div>
                    </div>
                  );
                })}
              </div>
            </div>
          )}
        </div>
      </AccordionContent>
    </AccordionItem>
  );
});
