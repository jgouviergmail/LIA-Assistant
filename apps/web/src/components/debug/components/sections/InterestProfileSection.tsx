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
import { Star } from 'lucide-react';
import {
  ActionBadge,
  DebugChip,
  DebugSection,
  EmptySection,
  ScoreBar,
  SubSectionHeader,
} from '../shared';
import { ExtractionLLMFooter } from './MemoryDetectionSection';
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

  return (
    <div className="flex flex-col gap-1 rounded bg-muted/10 px-2 py-2 text-xs">
      <div className="flex items-center gap-2">
        {/* Action badge */}
        <ActionBadge action={action} />

        {/* Topic */}
        <span className="flex-shrink-0 truncate font-medium text-foreground" title={interest.topic}>
          {interest.topic || '(deleted)'}
        </span>

        {/* Category badge */}
        {interest.category && <DebugChip tone="info">{interest.category}</DebugChip>}

        {/* Confidence bar (only for create/consolidate) */}
        {action !== 'delete' && confidence > 0 && (
          <ScoreBar score={confidence} space="confidence" className="ml-auto" />
        )}
      </div>

      {/* Decision reason */}
      {decision?.reason && (
        <div className="pl-4 text-[10px] text-muted-foreground">
          {decision.matched_interest ? (
            <>
              <span className="text-primary">{decision.matched_interest}</span>
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
      <EmptySection
        value="interest-profile"
        title="Interest Extraction"
        icon={Star}
        message={
          data?.enabled === false
            ? 'Interest extraction is globally disabled.'
            : 'No extraction data for this request.'
        }
      />
    );
  }

  if (!data.analyzed) {
    return (
      <EmptySection
        value="interest-profile"
        title="Interest Extraction"
        icon={Star}
        message={`Skipped: ${data.analysis_skipped_reason ?? 'not analyzed'}`}
      />
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
    <DebugSection
      value="interest-profile"
      title="Interest Extraction"
      icon={Star}
      badge={
        <>
          <DebugChip tone={hasActions ? 'success' : 'neutral'}>{interests.length}</DebugChip>
          {creates + consolidates > 0 && (
            <DebugChip tone="success">+{creates + consolidates}</DebugChip>
          )}
          {updates > 0 && <DebugChip tone="warning">~{updates}</DebugChip>}
          {deletes > 0 && <DebugChip tone="destructive">-{deletes}</DebugChip>}
        </>
      }
    >
      {hasActions ? (
        <div className="space-y-1">
          <SubSectionHeader label={`Actions (${interests.length})`} />
          <div className="space-y-1.5">
            {interests.map((interest, index) => (
              <ExtractedInterestRow
                key={`${interest.topic}-${index}`}
                interest={interest}
                decision={
                  decisionsByTopic.get(interest.topic) ??
                  (interest.interest_id ? decisionsByInterestId.get(interest.interest_id) : undefined)
                }
              />
            ))}
          </div>
        </div>
      ) : (
        <div className="rounded bg-muted/20 p-2 text-xs italic text-muted-foreground">
          No interest actions for this message.
        </div>
      )}

      {data.llm_metadata && <ExtractionLLMFooter metadata={data.llm_metadata} />}

      {data.error && (
        <div className="border-t border-border/50 pt-2 text-xs text-destructive">
          <strong>Error:</strong> {data.error}
        </div>
      )}
    </DebugSection>
  );
});
