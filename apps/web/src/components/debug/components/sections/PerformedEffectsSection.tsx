/**
 * Performed Effects Section (ADR-263)
 *
 * What the turn actually DID, read back from the effect register rather than
 * reconstructed from the stream. The panel and the user's action journal query
 * the same rows, so an admin and a user can never be told different stories
 * about the same turn.
 *
 * Admin surface: the tool name is shown here (it is meaningless to a user, and
 * decisive when diagnosing which capability acted).
 */

import React from 'react';
import { CheckCircle2, ListChecks, XCircle } from 'lucide-react';
import { DebugChip, DebugSection, MetricRow, SubSectionHeader } from '../shared';
import type { PerformedEffectsMetrics } from '@/types/chat';

export interface PerformedEffectsSectionProps {
  data: PerformedEffectsMetrics | undefined;
}

export const PerformedEffectsSection = React.memo(function PerformedEffectsSection({
  data,
}: PerformedEffectsSectionProps) {
  // Absent when the turn changed nothing — the common case.
  if (!data || data.count === 0) return null;

  const failed = data.failed_count ?? 0;

  return (
    <DebugSection
      value="performed_effects"
      title="Performed Effects"
      icon={ListChecks}
      badge={
        <>
          <DebugChip tone="info">×{data.count}</DebugChip>
          {failed > 0 && <DebugChip tone="destructive">{failed} failed</DebugChip>}
        </>
      }
    >
      <div className="space-y-1">
        <SubSectionHeader label="Recorded in the effect ledger" />
        {data.entries.map((entry, index) => (
          <div key={`${entry.tool_name}-${index}`} className="flex items-center gap-1.5">
            {entry.status === 'failed' ? (
              <XCircle className="h-3 w-3 shrink-0 text-destructive" aria-hidden="true" />
            ) : (
              <CheckCircle2 className="h-3 w-3 shrink-0 text-emerald-500" aria-hidden="true" />
            )}
            <div className="min-w-0 flex-1">
              <MetricRow label={entry.tool_name || entry.label_key} value={entry.status} mono />
            </div>
          </div>
        ))}
      </div>
    </DebugSection>
  );
});
