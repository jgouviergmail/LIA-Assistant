/**
 * Query Section Component
 *
 * Displays user query transformations through the pipeline — the INPUT of
 * the whole run, so it opens the panel's execution-ordered reading.
 */

import React from 'react';
import { MessageSquareText } from 'lucide-react';
import { DebugChip, DebugSection, SubSectionHeader } from '../shared';
import type { DebugMetrics } from '@/types/chat';

export interface QuerySectionProps {
  /** Query information metrics */
  data: DebugMetrics['query_info'];
  /** Execution engine of the turn (pipeline | react), when known */
  executionMode?: string;
}

/**
 * Query Section
 *
 * Clearly displays:
 * - The original user query
 * - The English translation for processing
 * - The enriched query with resolved context
 */
export const QuerySection = React.memo(function QuerySection({
  data,
  executionMode,
}: QuerySectionProps) {
  return (
    <DebugSection
      value="query"
      title="Query"
      icon={MessageSquareText}
      badge={
        <>
          <DebugChip tone="neutral">{data.user_language.toUpperCase()}</DebugChip>
          {executionMode && (
            <DebugChip tone={executionMode === 'react' ? 'info' : 'neutral'}>
              {executionMode}
            </DebugChip>
          )}
        </>
      }
    >
      {/* Transformation pipeline */}
      <div className="space-y-2">
        <SubSectionHeader label="Transformation pipeline" />

        {/* Original query */}
        <div>
          <div className="mb-0.5 text-[10px] uppercase tracking-wide text-muted-foreground">
            Original query
          </div>
          <div className="rounded border border-border/50 bg-muted/50 p-2 text-xs">
            {data.original_query}
          </div>
        </div>

        {/* Transformation arrow */}
        <div className="flex items-center justify-center">
          <span className="text-xs text-muted-foreground">↓ translation</span>
        </div>

        {/* English query */}
        <div>
          <div className="mb-0.5 text-[10px] uppercase tracking-wide text-muted-foreground">
            English query (processing)
          </div>
          <div className="rounded border border-border/50 bg-muted/50 p-2 text-xs">
            {data.english_query}
          </div>
        </div>

        {/* Enriched query if available */}
        {data.english_enriched_query && (
          <>
            <div className="flex items-center justify-center">
              <span className="text-xs text-muted-foreground">↓ enrichment</span>
            </div>
            <div>
              <div className="mb-0.5 text-[10px] uppercase tracking-wide text-muted-foreground">
                Enriched query
              </div>
              <div className="rounded border border-primary/20 bg-primary/10 p-2 text-xs font-medium">
                {data.english_enriched_query}
              </div>
            </div>
          </>
        )}
      </div>
    </DebugSection>
  );
});
