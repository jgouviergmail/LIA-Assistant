/**
 * LLM Calls Section Component
 *
 * Displays LLM calls and cost summary.
 * Dark mode compatible with detailed token breakdown.
 */

import React from 'react';
import { AccordionItem, AccordionTrigger, AccordionContent } from '@/components/ui/accordion';
import { MetricRow, EmptySection } from '../shared';
import { getNodeColor, MODEL_NAME_TRUNCATE_LENGTH } from '../../utils/constants';
import { formatTokenCount, formatCost, truncateText } from '../../utils/formatters';
import { cn } from '@/lib/utils';
import type { DebugMetrics } from '@/types/chat';

export interface LLMCallsSectionProps {
  /** List of LLM calls (can be undefined) */
  calls: DebugMetrics['llm_calls'];
  /** LLM calls summary (can be undefined) */
  summary: DebugMetrics['llm_summary'];
}

/**
 * Section LLM Calls
 *
 * Displays:
 * - Global summary (total calls, tokens in/out/cache, cost)
 * - Detailed list of calls per node (router, planner, response)
 * - Tokens and costs per call
 * - Cache efficiency (percentage)
 *
 * Not displayed if calls/summary is undefined (no LLM calls).
 */
export const LLMCallsSection = React.memo(function LLMCallsSection({
  calls,
  summary,
}: LLMCallsSectionProps) {
  if (!calls || !summary || calls.length === 0) {
    return <EmptySection value="llm" title="LLM Calls" />;
  }

  // Calculate cache efficiency
  const totalInputTokens = summary.total_tokens_in + summary.total_tokens_cache;
  const cacheEfficiency =
    totalInputTokens > 0 ? Math.round((summary.total_tokens_cache / totalInputTokens) * 100) : 0;

  return (
    <AccordionItem value="llm">
      <AccordionTrigger className="py-2 text-sm">
        <div className="flex items-center gap-2">
          <span>LLM Calls</span>
          <span className="text-xs bg-muted text-muted-foreground px-2 py-0.5 rounded border border-border">
            {summary.total_calls} calls
          </span>
          <span className="text-xs text-primary font-mono">
            {formatCost(summary.total_cost_eur)}
          </span>
        </div>
      </AccordionTrigger>
      <AccordionContent>
        <div className="space-y-3">
          {/* Global summary */}
          <div className="p-2 bg-muted/30 rounded border border-border/50">
            <div className="text-xs text-muted-foreground font-medium mb-1.5">Résumé</div>
            <div className="grid grid-cols-2 gap-x-4 gap-y-1">
              <MetricRow label="Tokens In" value={formatTokenCount(summary.total_tokens_in)} />
              <MetricRow label="Tokens Out" value={formatTokenCount(summary.total_tokens_out)} />
              <MetricRow
                label="Tokens Cache"
                value={formatTokenCount(summary.total_tokens_cache)}
                valueClassName="text-green-400"
              />
              <MetricRow
                label="Efficacité cache"
                value={`${cacheEfficiency}%`}
                valueClassName={
                  cacheEfficiency > 50 ? 'text-green-400 font-medium' : 'text-muted-foreground'
                }
              />
            </div>
            <div className="mt-2 pt-2 border-t border-border/30">
              <MetricRow
                label="Coût total"
                value={formatCost(summary.total_cost_eur)}
                highlight
                mono
                valueClassName="text-primary font-semibold"
              />
            </div>
          </div>

          {/* Detailed calls list */}
          <div className="border-t border-border/50 pt-2">
            <div className="text-xs text-muted-foreground font-medium mb-2">Détail par node</div>
            <div className="space-y-2">
              {calls.map((call, index) => {
                const nodeColorClass = getNodeColor(call.node_name);
                const callType = call.call_type ?? 'chat';
                const isEmbedding = callType === 'embedding';

                // Calculate per-call cache efficiency
                const callInputTokens = call.tokens_in + call.tokens_cache;
                const callCachePercent =
                  callInputTokens > 0 ? Math.round((call.tokens_cache / callInputTokens) * 100) : 0;

                return (
                  <div
                    key={`${call.node_name}-${index}`}
                    className="border-l-2 border-border pl-3 pb-1"
                  >
                    {/* Header: type badge + node + model */}
                    <div className="flex items-center justify-between text-xs mb-1">
                      <div className="flex items-center gap-1">
                        <span
                          className={cn(
                            'text-[10px] px-1 py-0.5 rounded uppercase font-medium border',
                            isEmbedding
                              ? 'bg-teal-500/20 text-teal-400 border-teal-500/30'
                              : 'bg-blue-500/20 text-blue-400 border-blue-500/30'
                          )}
                        >
                          {isEmbedding ? 'EMB' : 'CHAT'}
                        </span>
                        <span
                          className={cn(
                            'text-[10px] px-1.5 py-0.5 rounded uppercase font-medium border',
                            nodeColorClass
                          )}
                        >
                          {call.node_name}
                        </span>
                      </div>
                      <span
                        className="font-mono text-[10px] text-muted-foreground truncate ml-2"
                        title={call.model_name}
                      >
                        {truncateText(call.model_name, MODEL_NAME_TRUNCATE_LENGTH)}
                      </span>
                    </div>

                    {/* Call metrics */}
                    <div className="text-[10px] text-muted-foreground space-y-0.5">
                      <div className="flex justify-between">
                        <span>In:</span>
                        <span className="font-mono">{formatTokenCount(call.tokens_in)}</span>
                      </div>
                      <div className="flex justify-between">
                        <span>Out:</span>
                        <span className="font-mono">
                          {isEmbedding && call.tokens_out === 0
                            ? '—'
                            : formatTokenCount(call.tokens_out)}
                        </span>
                      </div>
                      {call.tokens_cache > 0 && (
                        <div className="flex justify-between text-green-400">
                          <span>Cache:</span>
                          <span className="font-mono">
                            {formatTokenCount(call.tokens_cache)}
                            <span className="text-green-400/70 ml-1">({callCachePercent}%)</span>
                          </span>
                        </div>
                      )}
                      <div className="flex justify-between font-medium text-foreground pt-0.5 border-t border-border/30">
                        <span>Coût:</span>
                        <span className="font-mono text-primary">{formatCost(call.cost_eur)}</span>
                      </div>
                    </div>
                  </div>
                );
              })}
            </div>
          </div>
        </div>
      </AccordionContent>
    </AccordionItem>
  );
});
