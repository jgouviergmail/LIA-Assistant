/**
 * LLM Calls Section Component
 *
 * Displays LLM calls and cost summary with per-node detail.
 */

import React from 'react';
import { Cpu } from 'lucide-react';
import {
  DebugChip,
  DebugSection,
  EmptySection,
  MetricRow,
  NodeChip,
  SubSectionHeader,
} from '../shared';
import { MODEL_NAME_TRUNCATE_LENGTH } from '../../utils/constants';
import { formatTokenCount, formatCost, truncateText } from '../../utils/formatters';
import { TONE_TEXT } from '../../utils/tones';
import { cn } from '@/lib/utils';
import type { DebugTone } from '../../utils/tones';
import type { DebugMetrics } from '@/types/chat';

export interface LLMCallsSectionProps {
  /** List of LLM calls (can be undefined) */
  calls: DebugMetrics['llm_calls'];
  /** LLM calls summary (can be undefined) */
  summary: DebugMetrics['llm_summary'];
}

const CALL_TYPE_CHIP: Record<string, { label: string; tone: DebugTone }> = {
  chat: { label: 'CHAT', tone: 'info' },
  embedding: { label: 'EMB', tone: 'neutral' },
  image_generation: { label: 'IMG', tone: 'warning' },
};

/**
 * Section LLM Calls
 *
 * Displays:
 * - Global summary (total calls, tokens in/out/cache, cost)
 * - Detailed list of calls per node (router, planner, response)
 * - Tokens and costs per call
 * - Cache efficiency (percentage)
 */
export const LLMCallsSection = React.memo(function LLMCallsSection({
  calls,
  summary,
}: LLMCallsSectionProps) {
  if (!calls || !summary || calls.length === 0) {
    return (
      <EmptySection
        value="llm"
        title="LLM Calls"
        icon={Cpu}
        message="No LLM call was recorded on this request."
      />
    );
  }

  // Cache efficiency
  const totalInputTokens = summary.total_tokens_in + summary.total_tokens_cache;
  const cacheEfficiency =
    totalInputTokens > 0 ? Math.round((summary.total_tokens_cache / totalInputTokens) * 100) : 0;

  return (
    <DebugSection
      value="llm"
      title="LLM Calls"
      icon={Cpu}
      badge={
        <>
          <DebugChip tone="neutral">{summary.total_calls} calls</DebugChip>
          <span className="font-mono text-xs text-primary">
            {formatCost(summary.total_cost_eur)}
          </span>
        </>
      }
    >
      {/* Global summary */}
      <div className="rounded border border-border/50 bg-muted/30 p-2">
        <SubSectionHeader label="Summary" />
        <div className="grid grid-cols-2 gap-x-4 gap-y-1">
          <MetricRow label="Tokens in" value={formatTokenCount(summary.total_tokens_in)} />
          <MetricRow label="Tokens out" value={formatTokenCount(summary.total_tokens_out)} />
          <MetricRow
            label="Tokens cache"
            value={formatTokenCount(summary.total_tokens_cache)}
            valueClassName={TONE_TEXT.success}
          />
          <MetricRow
            label="Cache efficiency"
            value={`${cacheEfficiency}%`}
            valueClassName={
              cacheEfficiency > 50 ? `${TONE_TEXT.success} font-medium` : 'text-muted-foreground'
            }
          />
        </div>
        <div className="mt-2 border-t border-border/30 pt-2">
          <MetricRow
            label="Total cost"
            value={formatCost(summary.total_cost_eur)}
            highlight
            mono
            valueClassName="text-primary font-semibold"
          />
        </div>
      </div>

      {/* Detailed calls list */}
      <div>
        <SubSectionHeader label="Detail per call" borderTop />
        <div className="space-y-2">
          {calls.map((call, index) => {
            const callType = call.call_type ?? 'chat';
            const typeChip = CALL_TYPE_CHIP[callType] ?? CALL_TYPE_CHIP.chat;

            // Per-call cache efficiency
            const callInputTokens = call.tokens_in + call.tokens_cache;
            const callCachePercent =
              callInputTokens > 0 ? Math.round((call.tokens_cache / callInputTokens) * 100) : 0;

            return (
              <div key={`${call.node_name}-${index}`} className="border-l-2 border-border pl-3 pb-1">
                {/* Header: type chip + node + model */}
                <div className="mb-1 flex items-center justify-between text-xs">
                  <div className="flex items-center gap-1">
                    <DebugChip tone={typeChip.tone}>{typeChip.label}</DebugChip>
                    <NodeChip nodeName={call.node_name} />
                  </div>
                  <span
                    className="ml-2 truncate font-mono text-[10px] text-muted-foreground"
                    title={call.model_name}
                  >
                    {truncateText(call.model_name, MODEL_NAME_TRUNCATE_LENGTH)}
                  </span>
                </div>

                {/* Call metrics */}
                <div className="space-y-0.5 text-[10px] text-muted-foreground">
                  <div className="flex justify-between">
                    <span>In:</span>
                    <span className="font-mono">{formatTokenCount(call.tokens_in)}</span>
                  </div>
                  <div className="flex justify-between">
                    <span>Out:</span>
                    <span className="font-mono">
                      {callType !== 'chat' && call.tokens_out === 0
                        ? '—'
                        : formatTokenCount(call.tokens_out)}
                    </span>
                  </div>
                  {call.tokens_cache > 0 && (
                    <div className={cn('flex justify-between', TONE_TEXT.success)}>
                      <span>Cache:</span>
                      <span className="font-mono">
                        {formatTokenCount(call.tokens_cache)}
                        <span className="ml-1 opacity-70">({callCachePercent}%)</span>
                      </span>
                    </div>
                  )}
                  <div className="flex justify-between border-t border-border/30 pt-0.5 font-medium text-foreground">
                    <span>Cost:</span>
                    <span className="font-mono text-primary">{formatCost(call.cost_eur)}</span>
                  </div>
                </div>
              </div>
            );
          })}
        </div>
      </div>
    </DebugSection>
  );
});
