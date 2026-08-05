/**
 * LLM Pipeline Section Component (v3.3 / v3.4)
 *
 * Chronological reconciliation of ALL LLM calls (chat + embedding + image).
 * v3.4 adds the WATERFALL: each call is positioned on the run timeline via
 * its run-anchored start offset, so serialization vs parallelism is read at
 * a glance instead of reconstructed from durations.
 */

import React from 'react';
import { Workflow } from 'lucide-react';
import { DebugChip, DebugSection, EmptySection, NodeChip, SubSectionHeader } from '../shared';
import { MODEL_NAME_TRUNCATE_LENGTH } from '../../utils/constants';
import { formatTokenCount, formatCost, formatDuration, truncateText } from '../../utils/formatters';
import { TONE_TEXT } from '../../utils/tones';
import { cn } from '@/lib/utils';
import type { DebugTone } from '../../utils/tones';
import type { LLMCall, LLMPipelineMetrics } from '@/types/chat';

export interface LLMPipelineSectionProps {
  /** Pipeline metrics (sorted chronologically) */
  data: LLMPipelineMetrics | undefined;
}

const CALL_TYPE_CHIP: Record<string, { label: string; tone: DebugTone }> = {
  chat: { label: 'CHAT', tone: 'info' },
  embedding: { label: 'EMB', tone: 'neutral' },
  image_generation: { label: 'IMG', tone: 'warning' },
};

/** Wall-clock span of the run: max(offset + duration) across calls. */
function wallMs(calls: LLMCall[]): number {
  return Math.max(...calls.map(c => (c.started_offset_ms ?? 0) + (c.duration_ms ?? 0)), 1);
}

/** True when at least one call carries a usable start offset. */
function hasOffsets(calls: LLMCall[]): boolean {
  return calls.some(c => (c.started_offset_ms ?? 0) > 0);
}

/**
 * Section LLM Pipeline
 *
 * Displays:
 * - Summary: total calls (chat + embedding), duration, tokens, cost
 * - Waterfall: every call positioned on the run timeline
 * - Chronological list of ALL LLM calls with type chip, timing, tokens
 */
export const LLMPipelineSection = React.memo(function LLMPipelineSection({
  data,
}: LLMPipelineSectionProps) {
  if (!data || data.calls.length === 0) {
    return (
      <EmptySection
        value="llm_pipeline"
        title="LLM Pipeline"
        icon={Workflow}
        message="No LLM call was recorded on this request."
      />
    );
  }

  const wall = wallMs(data.calls);
  const showWaterfall = hasOffsets(data.calls);

  return (
    <DebugSection
      value="llm_pipeline"
      title="LLM Pipeline"
      icon={Workflow}
      badge={
        <>
          <DebugChip tone="neutral">{data.total_calls} calls</DebugChip>
          {data.total_duration_ms > 0 && (
            <DebugChip tone="info">{formatDuration(data.total_duration_ms)}</DebugChip>
          )}
          <span className="font-mono text-xs text-primary">{formatCost(data.total_cost_eur)}</span>
        </>
      }
    >
      {/* Summary header */}
      <div className="rounded border border-border/50 bg-muted/30 p-2">
        <div className="text-xs text-muted-foreground">
          <span className="font-medium">{data.total_calls} calls</span>
          {' · '}
          {data.total_chat_calls} chat
          {data.total_embedding_calls > 0 && <> + {data.total_embedding_calls} emb</>}
          {' · '}
          <span className="text-primary">{formatDuration(data.total_duration_ms)}</span>
          {' · '}
          <span>{formatTokenCount(data.total_tokens_in + data.total_tokens_out)} tokens</span>
          {' · '}
          <span className="font-medium text-primary">{formatCost(data.total_cost_eur)}</span>
        </div>
      </div>

      {/* Waterfall: calls positioned on the run timeline */}
      {showWaterfall && (
        <div>
          <SubSectionHeader label="Waterfall (run timeline)" borderTop />
          <div className="space-y-1">
            {data.calls.map((call, index) => {
              const offset = call.started_offset_ms ?? 0;
              const duration = call.duration_ms ?? 0;
              const left = Math.min((offset / wall) * 100, 100);
              // A visible sliver even for near-instant calls.
              const width = Math.max((duration / wall) * 100, 1);

              return (
                <div key={`wf-${index}`} className="flex items-center gap-2">
                  <NodeChip nodeName={call.node_name} maxLength={16} className="w-28 shrink-0" />
                  <div className="relative h-2 flex-1 overflow-hidden rounded bg-muted/40">
                    {/* The bar carries POSITION; identity is on the NodeChip. */}
                    <div
                      data-testid="waterfall-bar"
                      className="absolute top-0 h-full rounded-sm bg-primary/70"
                      style={{ left: `${left}%`, width: `${Math.min(width, 100 - left)}%` }}
                      title={`${call.node_name}: starts at ${formatDuration(offset)}, lasts ${formatDuration(duration)}`}
                    />
                  </div>
                  <span className="w-12 shrink-0 text-right font-mono text-[10px] text-muted-foreground">
                    {duration ? formatDuration(duration) : '—'}
                  </span>
                </div>
              );
            })}
          </div>
          <div className="mt-1 flex justify-between text-[9px] text-muted-foreground">
            <span>0</span>
            <span>{formatDuration(wall)}</span>
          </div>
        </div>
      )}

      {/* Chronological call list */}
      <div>
        <SubSectionHeader label="Chronological order" borderTop />
        <div className="space-y-1">
          {data.calls.map((call, index) => {
            const callType = call.call_type ?? 'chat';
            const typeChip = CALL_TYPE_CHIP[callType] ?? CALL_TYPE_CHIP.chat;
            const seq = index + 1;

            return (
              <div
                key={`pipeline-${seq}`}
                className={cn(
                  'flex items-center gap-2 rounded px-2 py-1.5 text-[10px]',
                  index % 2 === 0 ? 'bg-muted/20' : ''
                )}
              >
                {/* Position number */}
                <span className="w-5 shrink-0 text-right font-mono text-muted-foreground">
                  #{seq}
                </span>

                {/* Type chip */}
                <DebugChip tone={typeChip.tone}>{typeChip.label}</DebugChip>

                {/* Node chip */}
                <NodeChip nodeName={call.node_name} maxLength={20} />

                {/* Model name */}
                <span
                  className="min-w-0 truncate font-mono text-muted-foreground"
                  title={call.model_name}
                >
                  {truncateText(call.model_name, MODEL_NAME_TRUNCATE_LENGTH)}
                </span>

                {/* Spacer */}
                <span className="flex-1" />

                {/* Duration */}
                <span className="w-12 shrink-0 text-right font-mono text-primary">
                  {call.duration_ms ? formatDuration(call.duration_ms) : '—'}
                </span>

                {/* Tokens: IN / CACHE / OUT */}
                <span className="w-28 shrink-0 text-right font-mono">
                  <span>{formatTokenCount(call.tokens_in)}</span>
                  <span className="mx-0.5 text-muted-foreground">/</span>
                  <span
                    className={call.tokens_cache > 0 ? TONE_TEXT.success : 'text-muted-foreground'}
                  >
                    {call.tokens_cache > 0 ? formatTokenCount(call.tokens_cache) : '—'}
                  </span>
                  <span className="mx-0.5 text-muted-foreground">/</span>
                  <span>
                    {callType !== 'chat' && call.tokens_out === 0
                      ? '—'
                      : formatTokenCount(call.tokens_out)}
                  </span>
                </span>

                {/* Cost */}
                <span className="w-16 shrink-0 text-right font-mono text-primary">
                  {formatCost(call.cost_eur)}
                </span>
              </div>
            );
          })}
        </div>
      </div>
    </DebugSection>
  );
});
