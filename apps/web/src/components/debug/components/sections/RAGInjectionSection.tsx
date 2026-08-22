/**
 * RAG Injection Section Component
 *
 * Displays RAG Knowledge Spaces injection metrics.
 *
 * Shows:
 * - Number of active spaces searched
 * - Chunks found vs injected
 * - The retrieval bounds in force, and the min_score drawn on every score bar
 * - Per-chunk details: space name, filename, relevance score
 */

import React from 'react';
import { FileSearch } from 'lucide-react';
import {
  DebugChip,
  DebugSection,
  EmptySection,
  MetricRow,
  RetrievalSettingsBar,
  ScoreBar,
  ScoreLegend,
  SectionBadge,
  SubSectionHeader,
} from '../shared';
import type { RAGInjectionMetrics } from '@/types/chat';

export interface RAGInjectionSectionProps {
  /** RAG injection metrics (can be undefined) */
  data: RAGInjectionMetrics | undefined;
}

/**
 * Section RAG Injection
 *
 * Displays Knowledge Spaces retrieval details:
 * - Spaces searched count
 * - Chunks found and injected
 * - Per-chunk score with the shared score bar
 */
export const RAGInjectionSection = React.memo(function RAGInjectionSection({
  data,
}: RAGInjectionSectionProps) {
  // Case: no data (RAG disabled or no active spaces)
  if (!data) {
    return (
      <EmptySection
        value="rag-injection"
        title="RAG Knowledge Spaces"
        icon={FileSearch}
        message="RAG is disabled or no space is active."
      />
    );
  }

  const hasChunks = data.chunks_injected > 0;

  return (
    <DebugSection
      value="rag-injection"
      title="RAG Knowledge Spaces"
      icon={FileSearch}
      badge={
        <>
          <SectionBadge
            passed={hasChunks}
            label={hasChunks ? `${data.chunks_injected} chunks` : 'NO MATCH'}
          />
          {data.spaces_searched > 0 && (
            <DebugChip tone="neutral">
              {data.spaces_searched} space{data.spaces_searched > 1 ? 's' : ''}
            </DebugChip>
          )}
        </>
      }
    >
      {data.settings && (
        <RetrievalSettingsBar
          minScore={data.settings.min_score}
          maxResults={data.settings.max_results}
        />
      )}

      {/* Summary metrics */}
      <div className="grid grid-cols-2 gap-x-4 gap-y-0.5">
        <MetricRow label="Spaces searched" value={data.spaces_searched} />
        <MetricRow label="Chunks found" value={data.chunks_found} />
        <MetricRow label="Chunks injected" value={data.chunks_injected} highlight={hasChunks} />
      </div>

      {/* Per-chunk details */}
      {data.chunks.length > 0 && (
        <div className="space-y-2 border-t border-border/50 pt-2">
          <SubSectionHeader label={`Injected chunks (${data.chunks.length})`} />
          <div className="max-h-48 space-y-1.5 overflow-y-auto">
            {data.chunks.map((chunk, index) => (
              <div key={index} className="rounded border border-border/50 bg-muted/30 p-2 text-xs">
                <div className="flex items-center justify-between gap-2">
                  <div className="min-w-0 flex-1">
                    <div className="truncate font-medium text-primary">{chunk.file}</div>
                    <div className="mt-0.5 truncate text-muted-foreground">
                      Space: {chunk.space}
                    </div>
                  </div>
                  <ScoreBar
                    score={chunk.score}
                    space="relevance"
                    threshold={data.settings?.min_score}
                    className="shrink-0"
                  />
                </div>
              </div>
            ))}
          </div>

          {/* Score legend */}
          <ScoreLegend space="relevance" />
        </div>
      )}

      {/* No results message */}
      {!hasChunks && data.spaces_searched > 0 && (
        <div className="mt-1 rounded border border-warning/30 bg-warning/10 p-2 text-xs text-warning">
          <strong>No relevant chunks:</strong> no document scored at or above the retrieval
          threshold
          {data.settings ? ` (min_score ${data.settings.min_score})` : ''}.
        </div>
      )}
    </DebugSection>
  );
});
