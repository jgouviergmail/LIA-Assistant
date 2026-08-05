/**
 * Image Generation Section Component (v3.4)
 *
 * Paid image-generation API calls of the run. The backend emitted this
 * payload for a long time — the panel simply never displayed it (only a
 * synthetic cost row in the LLM list).
 */

import React from 'react';
import { Image as ImageIcon } from 'lucide-react';
import {
  DebugChip,
  DebugSection,
  MetricRow,
  SubSectionHeader,
} from '../shared';
import { formatCost, formatDuration } from '../../utils/formatters';
import type { ImageGenerationCall, ImageGenerationSummary } from '@/types/chat';

export interface ImageGenerationSectionProps {
  calls: ImageGenerationCall[] | undefined;
  summary: ImageGenerationSummary | undefined;
}

export const ImageGenerationSection = React.memo(function ImageGenerationSection({
  calls,
  summary,
}: ImageGenerationSectionProps) {
  // Absent when no image was generated: the orchestrator folds this section
  // away entirely rather than showing a permanent N/A.
  if (!calls || !summary || calls.length === 0) return null;

  return (
    <DebugSection
      value="image_generation"
      title="Image Generation"
      icon={ImageIcon}
      badge={
        <>
          <DebugChip tone="warning">{summary.total_images} images</DebugChip>
          <span className="font-mono text-xs text-primary">
            {formatCost(summary.total_cost_eur)}
          </span>
        </>
      }
    >
      {/* Summary */}
      <div className="rounded border border-border/50 bg-muted/30 p-2">
        <SubSectionHeader label="Summary" />
        <div className="grid grid-cols-2 gap-x-4 gap-y-1">
          <MetricRow label="Calls" value={summary.total_calls} />
          <MetricRow label="Images" value={summary.total_images} highlight />
          <MetricRow
            label="Cost USD"
            value={`$${summary.total_cost_usd.toFixed(4)}`}
            valueClassName="font-mono"
          />
          <MetricRow
            label="Cost EUR"
            value={formatCost(summary.total_cost_eur)}
            valueClassName="font-mono text-primary"
          />
        </div>
      </div>

      {/* Per-call details */}
      <div>
        <SubSectionHeader label="Detail per call" borderTop />
        <div className="space-y-2">
          {calls.map((call, index) => (
            <div key={index} className="border-l-2 border-border pl-3 pb-1">
              <div className="mb-1 flex flex-wrap items-center gap-1.5 text-xs">
                <span className="font-mono font-medium">{call.model}</span>
                <DebugChip tone="neutral">{call.quality}</DebugChip>
                <DebugChip tone="neutral">{call.size}</DebugChip>
                <DebugChip tone="warning">
                  {call.image_count} image{call.image_count > 1 ? 's' : ''}
                </DebugChip>
              </div>
              <div className="space-y-0.5 text-[10px] text-muted-foreground">
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
                {call.prompt_preview && (
                  <div className="mt-1 truncate italic" title={call.prompt_preview}>
                    “{call.prompt_preview}”
                  </div>
                )}
              </div>
            </div>
          ))}
        </div>
      </div>
    </DebugSection>
  );
});
