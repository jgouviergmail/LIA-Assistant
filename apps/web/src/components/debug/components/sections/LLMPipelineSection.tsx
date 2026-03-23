/**
 * LLM Pipeline Section Component (v3.3)
 *
 * Chronological reconciliation of ALL LLM calls (chat + embedding).
 * Shows every call in execution order with timing, tokens, and cost.
 * Dark mode compatible.
 */

import React from 'react';
import { AccordionItem, AccordionTrigger, AccordionContent } from '@/components/ui/accordion';
import { getNodeColor, MODEL_NAME_TRUNCATE_LENGTH } from '../../utils/constants';
import { formatTokenCount, formatCost, formatDuration, truncateText } from '../../utils/formatters';
import { cn } from '@/lib/utils';
import type { LLMPipelineMetrics } from '@/types/chat';

export interface LLMPipelineSectionProps {
  /** Pipeline metrics (sorted chronologically) */
  data: LLMPipelineMetrics | undefined;
}

/**
 * Section LLM Pipeline (v3.3)
 *
 * Displays:
 * - Summary: total calls (chat + embedding), duration, tokens, cost
 * - Chronological list of ALL LLM calls with type badge, timing, tokens IN/CACHE/OUT
 *
 * Not displayed if data is undefined or empty.
 */
export const LLMPipelineSection = React.memo(function LLMPipelineSection({
  data,
}: LLMPipelineSectionProps) {
  if (!data || data.calls.length === 0) {
    return null;
  }

  return (
    <AccordionItem value="llm_pipeline">
      <AccordionTrigger className="py-2 text-sm">
        <div className="flex items-center gap-2">
          <span>LLM Pipeline</span>
          <span className="text-xs bg-muted text-muted-foreground px-2 py-0.5 rounded border border-border">
            {data.total_calls} appels
          </span>
          {data.total_duration_ms > 0 && (
            <span className="text-xs bg-blue-500/20 text-blue-400 px-2 py-0.5 rounded border border-blue-500/30">
              {formatDuration(data.total_duration_ms)}
            </span>
          )}
          <span className="text-xs text-primary font-mono">
            {formatCost(data.total_cost_eur)}
          </span>
        </div>
      </AccordionTrigger>
      <AccordionContent>
        <div className="space-y-3">
          {/* Summary header */}
          <div className="p-2 bg-muted/30 rounded border border-border/50">
            <div className="text-xs text-muted-foreground">
              <span className="font-medium">{data.total_calls} appels</span>
              {' · '}
              {data.total_chat_calls} chat
              {data.total_embedding_calls > 0 && (
                <> + {data.total_embedding_calls} emb</>
              )}
              {' · '}
              <span className="text-blue-400">{formatDuration(data.total_duration_ms)}</span>
              {' · '}
              <span>{formatTokenCount(data.total_tokens_in + data.total_tokens_out)} tokens</span>
              {' · '}
              <span className="text-primary font-medium">{formatCost(data.total_cost_eur)}</span>
            </div>
          </div>

          {/* Chronological call list */}
          <div className="border-t border-border/50 pt-2">
            <div className="text-xs text-muted-foreground font-medium mb-2">
              Ordre chronologique
            </div>
            <div className="space-y-1">
              {data.calls.map((call, index) => {
                const callType = call.call_type ?? 'chat';
                const isEmbedding = callType === 'embedding';
                const seq = call.sequence ?? index + 1;

                return (
                  <div
                    key={`pipeline-${seq}-${index}`}
                    className={cn(
                      'flex items-center gap-2 px-2 py-1.5 rounded text-[10px]',
                      index % 2 === 0 ? 'bg-muted/20' : ''
                    )}
                  >
                    {/* Sequence number */}
                    <span className="text-muted-foreground font-mono w-5 text-right shrink-0">
                      #{seq}
                    </span>

                    {/* Type badge */}
                    <span
                      className={cn(
                        'px-1 py-0.5 rounded uppercase font-medium border shrink-0',
                        isEmbedding
                          ? 'bg-teal-500/20 text-teal-400 border-teal-500/30'
                          : 'bg-blue-500/20 text-blue-400 border-blue-500/30'
                      )}
                    >
                      {isEmbedding ? 'EMB' : 'CHAT'}
                    </span>

                    {/* Node badge */}
                    <span
                      className={cn(
                        'px-1.5 py-0.5 rounded uppercase font-medium border shrink-0',
                        getNodeColor(call.node_name)
                      )}
                    >
                      {truncateText(call.node_name, 20)}
                    </span>

                    {/* Model name */}
                    <span
                      className="font-mono text-muted-foreground truncate min-w-0"
                      title={call.model_name}
                    >
                      {truncateText(call.model_name, MODEL_NAME_TRUNCATE_LENGTH)}
                    </span>

                    {/* Spacer */}
                    <span className="flex-1" />

                    {/* Duration */}
                    <span className="font-mono text-blue-400 shrink-0 w-12 text-right">
                      {call.duration_ms ? formatDuration(call.duration_ms) : '—'}
                    </span>

                    {/* Tokens: IN / CACHE / OUT */}
                    <span className="font-mono shrink-0 w-28 text-right">
                      <span>{formatTokenCount(call.tokens_in)}</span>
                      <span className="text-muted-foreground mx-0.5">/</span>
                      <span className={call.tokens_cache > 0 ? 'text-green-400' : 'text-muted-foreground'}>
                        {call.tokens_cache > 0 ? formatTokenCount(call.tokens_cache) : '—'}
                      </span>
                      <span className="text-muted-foreground mx-0.5">/</span>
                      <span>
                        {isEmbedding && call.tokens_out === 0
                          ? '—'
                          : formatTokenCount(call.tokens_out)}
                      </span>
                    </span>

                    {/* Cost */}
                    <span className="font-mono text-primary shrink-0 w-16 text-right">
                      {formatCost(call.cost_eur)}
                    </span>
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
