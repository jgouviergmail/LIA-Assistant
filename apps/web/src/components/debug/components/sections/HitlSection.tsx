/**
 * HITL Section Component (v3.4)
 *
 * The human-in-the-loop trace of the turn: either THIS run ended waiting
 * on the user (interrupt), or it is the resumed run carrying the user's
 * decision (approval, clarification, FOR_EACH cancellation).
 */

import React from 'react';
import { UserCheck } from 'lucide-react';
import { DebugChip, DebugSection, MetricRow, SubSectionHeader } from '../shared';
import type { HitlMetrics } from '@/types/chat';

export interface HitlSectionProps {
  data: HitlMetrics | undefined;
}

export const HitlSection = React.memo(function HitlSection({ data }: HitlSectionProps) {
  // Absent when the turn involved no human gate: folded away entirely.
  if (!data) return null;

  return (
    <DebugSection
      value="hitl"
      title="Human in the Loop"
      icon={UserCheck}
      badge={
        data.interrupted ? (
          <DebugChip tone="warning">INTERRUPTED</DebugChip>
        ) : (
          <DebugChip tone="success">RESUMED</DebugChip>
        )
      }
    >
      {data.interrupted && (
        <div className="space-y-1">
          <SubSectionHeader label="Interrupt" />
          <div className="rounded border border-warning/30 bg-warning/10 p-2 text-xs">
            This run stopped and is <strong>waiting for the user&apos;s decision</strong>.
          </div>
          {data.interrupt_action_type && (
            <MetricRow label="Action type" value={data.interrupt_action_type} mono />
          )}
          {data.interrupt_tool_name && (
            <MetricRow label="Tool" value={data.interrupt_tool_name} mono />
          )}
        </div>
      )}

      {(data.plan_approved || data.clarification_response || data.for_each_cancelled) && (
        <div className="space-y-1">
          <SubSectionHeader label="User decision" borderTop={data.interrupted} />
          {data.plan_approved && <MetricRow label="Plan approved" value highlight />}
          {data.clarification_field && (
            <MetricRow label="Clarified field" value={data.clarification_field} mono />
          )}
          {data.clarification_response && (
            <div className="rounded bg-muted/20 p-2 text-xs italic">
              “{data.clarification_response}”
            </div>
          )}
          {data.for_each_cancelled && (
            <MetricRow
              label="Bulk operation"
              value={`cancelled${data.cancellation_reason ? ` (${data.cancellation_reason})` : ''}`}
            />
          )}
        </div>
      )}
    </DebugSection>
  );
});
