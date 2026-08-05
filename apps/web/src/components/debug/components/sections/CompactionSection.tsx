/**
 * Context Compaction Section Component (v3.4)
 *
 * Context compaction of the session: strategy, tokens saved, messages
 * folded into the running summary. Previously only visible in logs.
 */

import React from 'react';
import { Archive } from 'lucide-react';
import { DebugChip, DebugSection, MetricRow, SubSectionHeader } from '../shared';
import { formatTokenCount } from '../../utils/formatters';
import type { CompactionMetrics } from '@/types/chat';

export interface CompactionSectionProps {
  data: CompactionMetrics | undefined;
}

export const CompactionSection = React.memo(function CompactionSection({
  data,
}: CompactionSectionProps) {
  // Absent when the session never compacted: folded away entirely.
  if (!data || data.count === 0) return null;

  return (
    <DebugSection
      value="compaction"
      title="Context Compaction"
      icon={Archive}
      badge={
        <>
          <DebugChip tone="info">×{data.count}</DebugChip>
          {data.tokens_saved !== null && data.tokens_saved !== undefined && (
            <DebugChip tone="success">-{formatTokenCount(data.tokens_saved)} tokens</DebugChip>
          )}
        </>
      }
    >
      <div className="space-y-1">
        <SubSectionHeader label="Last compaction" />
        {data.strategy && <MetricRow label="Strategy" value={data.strategy} mono />}
        {data.tokens_saved !== null && data.tokens_saved !== undefined && (
          <MetricRow label="Tokens saved" value={formatTokenCount(data.tokens_saved)} highlight />
        )}
        {data.messages_removed !== null && data.messages_removed !== undefined && (
          <MetricRow label="Messages folded" value={data.messages_removed} />
        )}
        <MetricRow label="Compactions this session" value={data.count} />
      </div>

      {data.summary_preview && (
        <div className="space-y-1">
          <SubSectionHeader label="Summary preview" borderTop />
          <div className="max-h-32 overflow-y-auto rounded border border-border/50 bg-muted/30 p-2 text-xs text-muted-foreground">
            {data.summary_preview}
          </div>
        </div>
      )}
    </DebugSection>
  );
});
