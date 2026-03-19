/**
 * Interest Detection Section Component
 *
 * Displays interest detection in the current message.
 * Uses LLM analysis (results cached in Redis).
 *
 * Shows:
 * - Interests extracted from the message with their confidence
 * - Matching decisions (consolidate vs create new)
 * - LLM metadata (tokens, model)
 *
 * v3.4: LLM-based detection display
 */

import React from 'react';
import { AccordionItem, AccordionTrigger, AccordionContent } from '@/components/ui/accordion';
import { cn } from '@/lib/utils';
import { SectionBadge } from '../shared';
import { INFO_SECTION_CLASSES, DEBUG_TEXT_SIZES } from '../../utils/constants';
import { formatPercent } from '../../utils/formatters';
import type { InterestProfileMetrics, ExtractedInterest, MatchingDecision } from '@/types/chat';

export interface InterestProfileSectionProps {
  /** Interest detection metrics (can be undefined) */
  data: InterestProfileMetrics | undefined;
}

/**
 * Displays an extracted interest with its confidence
 */
const ExtractedInterestRow = React.memo(function ExtractedInterestRow({
  interest,
  decision,
}: {
  interest: ExtractedInterest;
  decision?: MatchingDecision;
}) {
  const barWidth = interest.confidence * 100;
  const isConsolidate = decision?.action === 'consolidate';

  return (
    <div className="flex flex-col gap-1 text-xs py-2 px-2 bg-muted/10 rounded">
      <div className="flex items-center gap-2">
        {/* Confidence indicator */}
        <span
          className={cn(
            'w-2 h-2 rounded-full flex-shrink-0',
            interest.confidence >= 0.8
              ? 'bg-green-500'
              : interest.confidence >= 0.5
                ? 'bg-yellow-500'
                : 'bg-orange-500'
          )}
          title={`Confiance: ${formatPercent(interest.confidence)}`}
        />

        {/* Topic */}
        <span className="flex-shrink-0 font-medium text-foreground" title={interest.topic}>
          {interest.topic}
        </span>

        {/* Category badge */}
        <span
          className={cn(
            'text-[10px] px-1.5 py-0.5 rounded border flex-shrink-0',
            'bg-primary/10 text-primary/80 border-primary/20'
          )}
        >
          {interest.category}
        </span>

        {/* Confidence bar + value */}
        <div className="flex-1 flex items-center gap-2 min-w-0">
          <div className="relative h-1.5 bg-muted/30 rounded-full flex-1 max-w-[80px]">
            <div
              className={cn(
                'absolute left-0 top-0 h-full rounded-full transition-all',
                interest.confidence >= 0.8
                  ? 'bg-green-500'
                  : interest.confidence >= 0.5
                    ? 'bg-yellow-500'
                    : 'bg-orange-500'
              )}
              style={{ width: `${barWidth}%` }}
            />
          </div>
          <span
            className={`font-mono ${DEBUG_TEXT_SIZES.mono} w-12 text-right text-muted-foreground`}
          >
            {formatPercent(interest.confidence)}
          </span>
        </div>
      </div>

      {/* Decision row */}
      {decision && (
        <div className="flex items-center gap-2 pl-4 text-[10px]">
          <span
            className={cn(
              'px-1.5 py-0.5 rounded border',
              isConsolidate
                ? 'bg-blue-500/20 text-blue-400 border-blue-500/30'
                : 'bg-green-500/20 text-green-400 border-green-500/30'
            )}
          >
            {isConsolidate ? 'CONSOLIDER' : 'NOUVEAU'}
          </span>
          {isConsolidate && decision.matched_interest && (
            <span className="text-muted-foreground">→ {decision.matched_interest}</span>
          )}
        </div>
      )}
    </div>
  );
});

/**
 * Section Interest Detection
 *
 * Displays interest detection in the current message:
 * - Interests extracted by the LLM with their confidence
 * - Deduplication decisions (consolidate vs create)
 * - LLM metadata (tokens used)
 */
export const InterestProfileSection = React.memo(function InterestProfileSection({
  data,
}: InterestProfileSectionProps) {
  // Case: no data or feature disabled
  if (!data || !data.enabled) {
    return (
      <AccordionItem value="interest-profile">
        <AccordionTrigger className="py-2 text-sm">
          <div className="flex items-center gap-2">
            <span>Interest Detection</span>
            <SectionBadge passed={false} label={data?.enabled === false ? 'OFF' : 'N/A'} />
          </div>
        </AccordionTrigger>
        <AccordionContent>
          <div className={INFO_SECTION_CLASSES}>
            {data?.enabled === false ? (
              <>
                <strong>Disabled:</strong> Interest learning is globally disabled.
              </>
            ) : (
              <>
                <strong>Not available:</strong> No detection data.
              </>
            )}
          </div>
        </AccordionContent>
      </AccordionItem>
    );
  }

  // Case: analysis not performed (e.g., message too short)
  if (!data.analyzed) {
    return (
      <AccordionItem value="interest-profile">
        <AccordionTrigger className="py-2 text-sm">
          <div className="flex items-center gap-2">
            <span>Interest Detection</span>
            <SectionBadge passed={false} label="SKIP" />
          </div>
        </AccordionTrigger>
        <AccordionContent>
          <div className={INFO_SECTION_CLASSES}>
            <strong>Not analyzed:</strong>{' '}
            {data.analysis_skipped_reason || 'Analysis skipped (message too short or not relevant)'}
          </div>
        </AccordionContent>
      </AccordionItem>
    );
  }

  const extractedCount = data.extracted_interests?.length ?? 0;
  const hasExtracted = extractedCount > 0;

  // Map decisions by topic for easy lookup
  const decisionsByTopic = new Map<string, MatchingDecision>();
  data.matching_decisions?.forEach(d => {
    decisionsByTopic.set(d.extracted_topic, d);
  });

  // Header badge showing extracted count
  const headerBadge = hasExtracted ? `${extractedCount}` : '0';

  return (
    <AccordionItem value="interest-profile">
      <AccordionTrigger className="py-2 text-sm">
        <div className="flex items-center gap-2">
          <span>Interest Detection</span>
          <span
            className={cn(
              'text-xs px-1.5 py-0.5 rounded font-medium border',
              hasExtracted
                ? 'bg-green-500/20 text-green-400 border-green-500/30'
                : 'bg-muted/50 text-muted-foreground border-border/50'
            )}
          >
            {headerBadge}
          </span>
        </div>
      </AccordionTrigger>
      <AccordionContent>
        <div className="space-y-3">
          {/* Extracted interests list */}
          {hasExtracted ? (
            <div className="space-y-1">
              <div className="text-xs text-muted-foreground font-medium mb-1">
                Detected interests ({extractedCount})
              </div>
              <div className="space-y-1.5 max-h-[200px] overflow-y-auto">
                {data.extracted_interests.map((interest, index) => (
                  <ExtractedInterestRow
                    key={`${interest.topic}-${index}`}
                    interest={interest}
                    decision={decisionsByTopic.get(interest.topic)}
                  />
                ))}
              </div>
            </div>
          ) : (
            <div className="text-xs text-muted-foreground italic p-2 bg-muted/20 rounded">
              No interests detected in this message.
            </div>
          )}

          {/* LLM Metadata */}
          {data.llm_metadata && (
            <div className="border-t pt-2 flex flex-wrap items-center gap-3 text-[10px] text-muted-foreground">
              <span title="LLM Model">
                <strong>Model:</strong> {data.llm_metadata.model}
              </span>
              <span title="Input tokens">
                <strong>IN:</strong> {data.llm_metadata.input_tokens}
              </span>
              <span title="Output tokens">
                <strong>OUT:</strong> {data.llm_metadata.output_tokens}
              </span>
              {data.llm_metadata.cached_tokens > 0 && (
                <span title="Cached tokens">
                  <strong>CACHE:</strong> {data.llm_metadata.cached_tokens}
                </span>
              )}
            </div>
          )}

          {/* Legend */}
          {hasExtracted && (
            <div className="border-t pt-2 flex items-center gap-4 text-[10px] text-muted-foreground">
              <div className="flex items-center gap-1">
                <span className="w-2 h-2 rounded-full bg-green-500" />
                <span>&gt;80%</span>
              </div>
              <div className="flex items-center gap-1">
                <span className="w-2 h-2 rounded-full bg-yellow-500" />
                <span>50-80%</span>
              </div>
              <div className="flex items-center gap-1">
                <span className="w-2 h-2 rounded-full bg-orange-500" />
                <span>&lt;50%</span>
              </div>
            </div>
          )}

          {/* Error if any */}
          {data.error && (
            <div className="border-t pt-2 text-xs text-red-400">
              <strong>Error:</strong> {data.error}
            </div>
          )}
        </div>
      </AccordionContent>
    </AccordionItem>
  );
});
