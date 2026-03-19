/**
 * RAG Injection Section Component
 *
 * Displays RAG Knowledge Spaces injection metrics.
 *
 * Shows:
 * - Number of active spaces searched
 * - Chunks found vs injected
 * - Per-chunk details: space name, filename, relevance score
 *
 * Phase: evolution - RAG Spaces debug panel integration
 */

import React from 'react';
import { AccordionItem, AccordionTrigger, AccordionContent } from '@/components/ui/accordion';
import { cn } from '@/lib/utils';
import { MetricRow, SectionBadge } from '../shared';
import { CONFIDENCE_BAR_COLORS, SCORE_BAR_MAX_WIDTH_PX } from '../../utils/constants';
import type { RAGInjectionMetrics } from '@/types/chat';

export interface RAGInjectionSectionProps {
  /** RAG injection metrics (can be undefined) */
  data: RAGInjectionMetrics | undefined;
}

/**
 * Get color tier for a RAG relevance score
 */
function getScoreColor(score: number): 'high' | 'medium' | 'low' {
  if (score >= 0.7) return 'high';
  if (score >= 0.5) return 'medium';
  return 'low';
}

/**
 * Section RAG Injection
 *
 * Displays Knowledge Spaces retrieval details:
 * - Spaces searched count
 * - Chunks found and injected
 * - Per-chunk score with visual bars
 */
export const RAGInjectionSection = React.memo(function RAGInjectionSection({
  data,
}: RAGInjectionSectionProps) {
  // Case: no data (RAG disabled or no active spaces)
  if (!data) {
    return null;
  }

  const hasChunks = data.chunks_injected > 0;

  return (
    <AccordionItem value="rag-injection">
      <AccordionTrigger className="py-2 text-sm">
        <div className="flex items-center gap-2">
          <span>RAG Knowledge Spaces</span>
          <SectionBadge
            passed={hasChunks}
            label={hasChunks ? `${data.chunks_injected} chunks` : 'NO MATCH'}
          />
          {data.spaces_searched > 0 && (
            <span className="text-[10px] px-1.5 py-0.5 rounded font-medium bg-muted/50 text-muted-foreground border border-border/50">
              {data.spaces_searched} space{data.spaces_searched > 1 ? 's' : ''}
            </span>
          )}
        </div>
      </AccordionTrigger>
      <AccordionContent>
        <div className="space-y-3">
          {/* Summary metrics */}
          <div className="grid grid-cols-2 gap-x-4 gap-y-0.5">
            <MetricRow label="Spaces searched" value={data.spaces_searched} />
            <MetricRow label="Chunks found" value={data.chunks_found} />
            <MetricRow label="Chunks injected" value={data.chunks_injected} highlight={hasChunks} />
          </div>

          {/* Per-chunk details */}
          {data.chunks.length > 0 && (
            <div className="border-t pt-2 space-y-2">
              <div className="text-xs text-muted-foreground font-medium">
                Injected chunks ({data.chunks.length})
              </div>
              <div className="space-y-1.5 max-h-48 overflow-y-auto">
                {data.chunks.map((chunk, index) => {
                  const tier = getScoreColor(chunk.score);
                  const barWidth = Math.round(chunk.score * SCORE_BAR_MAX_WIDTH_PX);

                  return (
                    <div
                      key={index}
                      className="text-xs p-2 bg-muted/30 rounded border border-border/50"
                    >
                      <div className="flex items-center justify-between gap-2">
                        <div className="flex-1 min-w-0">
                          <div className="font-medium text-primary truncate">{chunk.file}</div>
                          <div className="text-muted-foreground mt-0.5 truncate">
                            Space: {chunk.space}
                          </div>
                        </div>
                        {/* Score with visual bar */}
                        <div className="flex items-center gap-2 shrink-0">
                          <div
                            className="h-1.5 rounded-full bg-muted/50"
                            style={{ width: `${SCORE_BAR_MAX_WIDTH_PX}px` }}
                          >
                            <div
                              className={cn(
                                'h-full rounded-full transition-all',
                                CONFIDENCE_BAR_COLORS[tier]
                              )}
                              style={{ width: `${barWidth}px` }}
                            />
                          </div>
                          <span
                            className={cn(
                              'text-[10px] font-mono w-10 text-right',
                              tier === 'high'
                                ? 'text-green-400'
                                : tier === 'medium'
                                  ? 'text-yellow-400'
                                  : 'text-red-400'
                            )}
                          >
                            {chunk.score.toFixed(3)}
                          </span>
                        </div>
                      </div>
                    </div>
                  );
                })}
              </div>

              {/* Score legend */}
              <div className="flex items-center gap-3 text-[9px] text-muted-foreground pt-1">
                <span className="flex items-center gap-1">
                  <span className="w-2 h-2 rounded-full bg-green-500" />
                  {'≥0.70'}
                </span>
                <span className="flex items-center gap-1">
                  <span className="w-2 h-2 rounded-full bg-yellow-500" />
                  0.50-0.69
                </span>
                <span className="flex items-center gap-1">
                  <span className="w-2 h-2 rounded-full bg-red-400" />
                  {'<0.50'}
                </span>
              </div>
            </div>
          )}

          {/* No results message */}
          {!hasChunks && data.spaces_searched > 0 && (
            <div className="mt-1 text-xs text-yellow-300 bg-yellow-900/20 p-2 rounded border border-yellow-700/50">
              <strong>No relevant chunks:</strong> No document content matched the query above the
              minimum score threshold.
            </div>
          )}
        </div>
      </AccordionContent>
    </AccordionItem>
  );
});
