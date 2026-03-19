/**
 * Query Info Section Component
 *
 * Displays user query transformations through the pipeline.
 */

import React from 'react';
import { AccordionItem, AccordionTrigger, AccordionContent } from '@/components/ui/accordion';
import type { DebugMetrics } from '@/types/chat';

export interface QuerySectionProps {
  /** Query information metrics */
  data: DebugMetrics['query_info'];
}

/**
 * Query Info Section
 *
 * Clearly displays:
 * - The original user query
 * - The English translation for processing
 * - The enriched query with resolved context
 */
export const QuerySection = React.memo(function QuerySection({ data }: QuerySectionProps) {
  return (
    <AccordionItem value="query">
      <AccordionTrigger className="py-2 text-sm">
        <div className="flex items-center gap-2">
          <span>Query Info</span>
          <span className="text-xs bg-muted text-muted-foreground px-1.5 py-0.5 rounded border border-border">
            {data.user_language.toUpperCase()}
          </span>
        </div>
      </AccordionTrigger>
      <AccordionContent>
        <div className="space-y-3">
          {/* Pipeline de transformation */}
          <div className="space-y-2">
            <div className="text-xs text-muted-foreground font-medium mb-1">
              Pipeline de transformation
            </div>

            {/* Original query */}
            <div>
              <div className="text-[10px] text-muted-foreground/70 uppercase tracking-wide mb-0.5">
                Requête originale
              </div>
              <div className="p-2 bg-muted/50 rounded text-xs border border-border/50">
                {data.original_query}
              </div>
            </div>

            {/* Transformation arrow */}
            <div className="flex items-center justify-center">
              <span className="text-muted-foreground/50 text-xs">↓ traduction</span>
            </div>

            {/* English query */}
            <div>
              <div className="text-[10px] text-muted-foreground/70 uppercase tracking-wide mb-0.5">
                Requête anglaise (traitement)
              </div>
              <div className="p-2 bg-muted/50 rounded text-xs border border-border/50">
                {data.english_query}
              </div>
            </div>

            {/* Enriched query if available */}
            {data.english_enriched_query && (
              <>
                <div className="flex items-center justify-center">
                  <span className="text-muted-foreground/50 text-xs">↓ enrichissement</span>
                </div>
                <div>
                  <div className="text-[10px] text-muted-foreground/70 uppercase tracking-wide mb-0.5">
                    Requête enrichie
                  </div>
                  <div className="p-2 bg-primary/10 rounded text-xs font-medium border border-primary/20">
                    {data.english_enriched_query}
                  </div>
                </div>
              </>
            )}
          </div>

          {/* Dead code removed (v3.1): implicit_intents, anticipated_needs, fallback_strategies
              These fields are always [] from backend - UI sections removed to avoid confusion */}
        </div>
      </AccordionContent>
    </AccordionItem>
  );
});
