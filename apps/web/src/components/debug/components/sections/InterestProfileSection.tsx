/**
 * Interest Extraction Section Component
 *
 * Displays interests created, updated, deleted, or consolidated by the
 * background extraction pipeline. Shows action type, topic, category,
 * confidence, and matching decisions.
 *
 * Aligned with Memory Extraction and Journal Extraction sections
 * for consistent create/update/delete action display.
 */

import React from 'react';
import { AccordionItem, AccordionTrigger, AccordionContent } from '@/components/ui/accordion';
import { cn } from '@/lib/utils';
import { ActionBadge, SectionBadge } from '../shared';
import { DEBUG_TEXT_SIZES, INFO_SECTION_CLASSES } from '../../utils/constants';
import { formatPercent } from '../../utils/formatters';
import type { InterestProfileMetrics, ExtractedInterest, MatchingDecision } from '@/types/chat';

export interface InterestProfileSectionProps {
  data: InterestProfileMetrics | undefined;
}

/**
 * Single extracted interest row with action badge
 */
function ExtractedInterestRow({
  interest,
  decision,
}: {
  interest: ExtractedInterest;
  decision?: MatchingDecision;
}) {
  const action = interest.action ?? decision?.action ?? 'create';
  const confidence = interest.confidence ?? 0;
  const barWidth = confidence * 100;

  return (
    <div className="flex flex-col gap-1 text-xs py-2 px-2 bg-muted/10 rounded">
      <div className="flex items-center gap-2">
        {/* Action badge */}
        <ActionBadge action={action} />

        {/* Topic */}
        <span className="flex-shrink-0 font-medium text-foreground truncate" title={interest.topic}>
          {interest.topic || '(deleted)'}
        </span>

        {/* Category badge */}
        {interest.category && (
          <span
            className={cn(
              'text-[10px] px-1.5 py-0.5 rounded border flex-shrink-0',
              'bg-primary/10 text-primary/80 border-primary/20'
            )}
          >
            {interest.category}
          </span>
        )}

        {/* Confidence bar (only for create/consolidate) */}
        {action !== 'delete' && confidence > 0 && (
          <div className="flex-1 flex items-center gap-2 min-w-0">
            <div className="relative h-1.5 bg-muted/30 rounded-full flex-1 max-w-[60px]">
              <div
                className={cn(
                  'absolute left-0 top-0 h-full rounded-full transition-all',
                  confidence >= 0.8
                    ? 'bg-green-500'
                    : confidence >= 0.5
                      ? 'bg-yellow-500'
                      : 'bg-orange-500'
                )}
                style={{ width: `${barWidth}%` }}
              />
            </div>
            <span
              className={`font-mono ${DEBUG_TEXT_SIZES.mono} w-10 text-right text-muted-foreground`}
            >
              {formatPercent(confidence)}
            </span>
          </div>
        )}
      </div>

      {/* Decision reason */}
      {decision?.reason && (
        <div className="pl-4 text-[10px] text-muted-foreground/60">
          {decision.matched_interest ? (
            <>
              <span className="text-blue-400">{decision.matched_interest}</span>
              <span> — {decision.reason}</span>
            </>
          ) : (
            decision.reason
          )}
        </div>
      )}
    </div>
  );
}

/**
 * Interest Extraction Section
 */
export const InterestProfileSection = React.memo(function InterestProfileSection({
  data,
}: InterestProfileSectionProps) {
  if (!data || !data.enabled) {
    return (
      <AccordionItem value="interest-profile">
        <AccordionTrigger className="py-2 text-sm">
          <div className="flex items-center gap-2">
            <span>Interest Extraction</span>
            <SectionBadge passed={false} label={data?.enabled === false ? 'OFF' : 'N/A'} />
          </div>
        </AccordionTrigger>
        <AccordionContent>
          <div className={INFO_SECTION_CLASSES}>
            {data?.enabled === false ? (
              <>
                <strong>Disabled:</strong> Interest extraction is globally disabled.
              </>
            ) : (
              <>
                <strong>Not available:</strong> No extraction data.
              </>
            )}
          </div>
        </AccordionContent>
      </AccordionItem>
    );
  }

  if (!data.analyzed) {
    return (
      <AccordionItem value="interest-profile">
        <AccordionTrigger className="py-2 text-sm">
          <div className="flex items-center gap-2">
            <span>Interest Extraction</span>
            <SectionBadge passed={false} label="SKIP" />
          </div>
        </AccordionTrigger>
        <AccordionContent>
          <div className={INFO_SECTION_CLASSES}>
            <strong>Skipped:</strong> {data.analysis_skipped_reason ?? 'Not analyzed'}
          </div>
        </AccordionContent>
      </AccordionItem>
    );
  }

  const interests = data.extracted_interests ?? [];
  const decisions = data.matching_decisions ?? [];
  const hasActions = interests.length > 0;

  // Build decision lookup by topic AND interest_id (for delete/update where topic may be missing)
  const decisionsByTopic = new Map<string, MatchingDecision>();
  const decisionsByInterestId = new Map<string, MatchingDecision>();
  for (const d of decisions) {
    if (d.extracted_topic) decisionsByTopic.set(d.extracted_topic, d);
    if (d.interest_id) decisionsByInterestId.set(d.interest_id, d);
  }

  // Count by action type from decisions (more accurate than interest.action alone)
  const creates = decisions.filter(d => d.action === 'create_new').length;
  const consolidates = decisions.filter(d => d.action === 'consolidate').length;
  const updates = decisions.filter(d => d.action === 'update').length;
  const deletes = decisions.filter(d => d.action === 'delete').length;

  return (
    <AccordionItem value="interest-profile">
      <AccordionTrigger className="py-2 text-sm">
        <div className="flex items-center gap-2">
          <span>Interest Extraction</span>
          <span
            className={cn(
              'text-xs px-1.5 py-0.5 rounded font-medium border',
              hasActions
                ? 'bg-emerald-500/20 text-emerald-400 border-emerald-500/30'
                : 'bg-muted/50 text-muted-foreground border-border/50'
            )}
          >
            {interests.length}
          </span>
          {/* Action type summary badges */}
          {creates + consolidates > 0 && (
            <span className="text-[9px] px-1 py-0.5 rounded bg-emerald-500/15 text-emerald-400">
              +{creates + consolidates}
            </span>
          )}
          {updates > 0 && (
            <span className="text-[9px] px-1 py-0.5 rounded bg-amber-500/15 text-amber-400">
              ~{updates}
            </span>
          )}
          {deletes > 0 && (
            <span className="text-[9px] px-1 py-0.5 rounded bg-red-500/15 text-red-400">
              -{deletes}
            </span>
          )}
        </div>
      </AccordionTrigger>
      <AccordionContent>
        <div className="space-y-3">
          {hasActions ? (
            <div className="space-y-1">
              <div className="text-xs text-muted-foreground font-medium mb-1">
                Actions ({interests.length})
              </div>
              <div className="space-y-1.5 space-y-1.5">
                {interests.map((interest, index) => (
                  <ExtractedInterestRow
                    key={`${interest.topic}-${index}`}
                    interest={interest}
                    decision={
                      decisionsByTopic.get(interest.topic) ??
                      (interest.interest_id
                        ? decisionsByInterestId.get(interest.interest_id)
                        : undefined)
                    }
                  />
                ))}
              </div>
            </div>
          ) : (
            <div className="text-xs text-muted-foreground italic p-2 bg-muted/20 rounded">
              No interest actions for this message.
            </div>
          )}

          {data.llm_metadata && (
            <div className="border-t pt-2 flex flex-wrap items-center gap-3 text-[10px] text-muted-foreground">
              <span>
                <strong>Model:</strong> {data.llm_metadata.model}
              </span>
              <span>
                <strong>IN:</strong> {data.llm_metadata.input_tokens}
              </span>
              <span>
                <strong>OUT:</strong> {data.llm_metadata.output_tokens}
              </span>
              {data.llm_metadata.cached_tokens > 0 && (
                <span>
                  <strong>CACHE:</strong> {data.llm_metadata.cached_tokens}
                </span>
              )}
            </div>
          )}

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
