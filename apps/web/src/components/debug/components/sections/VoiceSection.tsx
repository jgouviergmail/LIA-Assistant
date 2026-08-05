/**
 * Voice Synthesis Section Component (v3.4)
 *
 * Paid TTS calls of the turn. Arrives via debug_metrics_update because the
 * sync-fallback TTS path finishes after the main debug_metrics chunk.
 * Edge TTS is free and never recorded here.
 */

import React from 'react';
import { Volume2 } from 'lucide-react';
import { DebugChip, DebugSection, MetricRow, SubSectionHeader } from '../shared';
import { formatCost, formatDuration } from '../../utils/formatters';
import type { VoiceMetrics } from '@/types/chat';

export interface VoiceSectionProps {
  data: VoiceMetrics | undefined;
}

export const VoiceSection = React.memo(function VoiceSection({ data }: VoiceSectionProps) {
  // Absent when the turn produced no paid speech: folded away entirely.
  if (!data || data.total_calls === 0) return null;

  return (
    <DebugSection
      value="voice"
      title="Voice Synthesis"
      icon={Volume2}
      badge={
        <>
          <DebugChip tone="info">{data.total_calls} calls</DebugChip>
          <span className="font-mono text-xs text-primary">{formatCost(data.total_cost_eur)}</span>
        </>
      }
    >
      {/* Summary */}
      <div className="rounded border border-border/50 bg-muted/30 p-2">
        <SubSectionHeader label="Summary" />
        <div className="grid grid-cols-2 gap-x-4 gap-y-1">
          <MetricRow label="Calls" value={data.total_calls} />
          <MetricRow label="Characters" value={data.total_characters} highlight />
          <MetricRow
            label="Total cost"
            value={formatCost(data.total_cost_eur)}
            valueClassName="font-mono text-primary"
          />
        </div>
      </div>

      {/* Per-call details */}
      <div>
        <SubSectionHeader label="Detail per call" borderTop />
        <div className="space-y-2">
          {data.calls.map((call, index) => (
            <div key={index} className="border-l-2 border-border pl-3 pb-1">
              <div className="mb-1 flex items-center gap-1.5 text-xs">
                <DebugChip tone="neutral">{call.provider}</DebugChip>
                <span className="font-mono font-medium">{call.model}</span>
              </div>
              <div className="space-y-0.5 text-[10px] text-muted-foreground">
                <div className="flex justify-between">
                  <span>Characters:</span>
                  <span className="font-mono">{call.characters}</span>
                </div>
                {call.duration_ms > 0 && (
                  <div className="flex justify-between">
                    <span>Duration:</span>
                    <span className="font-mono">{formatDuration(call.duration_ms)}</span>
                  </div>
                )}
                <div className="flex justify-between font-medium text-foreground">
                  <span>Cost:</span>
                  <span className="font-mono text-primary">{formatCost(call.cost_eur)}</span>
                </div>
              </div>
            </div>
          ))}
        </div>
      </div>
    </DebugSection>
  );
});
