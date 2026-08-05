/**
 * Semantic Validator Section Component (v3.4)
 *
 * The validator's verdict on the plan. ADR-184 doctrine is displayed in
 * place: a verdict is INFORMATIVE, never a blocker — a rejected plan still
 * executes, and this section exists so that outcome can be understood
 * instead of imagined.
 */

import React from 'react';
import { ShieldCheck } from 'lucide-react';
import {
  DebugChip,
  DebugSection,
  EmptySection,
  MetricRow,
  SubSectionHeader,
} from '../shared';
import { formatPercent } from '../../utils/formatters';
import type { DebugTone } from '../../utils/tones';
import type { SemanticValidationMetrics } from '@/types/chat';

export interface SemanticValidatorSectionProps {
  data: SemanticValidationMetrics | undefined;
}

const CRITICALITY_TONE: Record<string, DebugTone> = {
  LOW: 'success',
  MEDIUM: 'warning',
  HIGH: 'destructive',
};

const SEVERITY_TONE: Record<string, DebugTone> = {
  low: 'neutral',
  medium: 'warning',
  high: 'destructive',
};

export const SemanticValidatorSection = React.memo(function SemanticValidatorSection({
  data,
}: SemanticValidatorSectionProps) {
  if (!data) {
    return (
      <EmptySection
        value="semantic_validation"
        title="Semantic Validator"
        icon={ShieldCheck}
        message="The validator did not run (no plan, or trivial single-step plan)."
      />
    );
  }

  return (
    <DebugSection
      value="semantic_validation"
      title="Semantic Validator"
      icon={ShieldCheck}
      anomaly={!data.is_valid}
      badge={
        <>
          <DebugChip tone={data.is_valid ? 'success' : 'warning'}>
            {data.is_valid ? 'VALID' : 'REJECTED'}
          </DebugChip>
          {data.criticality && (
            <DebugChip tone={CRITICALITY_TONE[data.criticality] ?? 'neutral'}>
              {data.criticality}
            </DebugChip>
          )}
        </>
      }
    >
      {/* Verdict */}
      <div className="space-y-1">
        <SubSectionHeader label="Verdict" />
        <MetricRow label="Valid" value={data.is_valid} highlight />
        <MetricRow label="Confidence" value={formatPercent(data.confidence)} highlight />
        <MetricRow label="Duration" value={`${data.validation_duration_seconds.toFixed(2)}s`} mono />
        {data.used_fallback && (
          <MetricRow
            label="Fallback"
            value={data.fallback_reason ?? 'timeout (optimistic pass)'}
          />
        )}
      </div>

      {/* ADR-184: the verdict is not a gate */}
      {!data.is_valid && (
        <div className="rounded border border-border/50 bg-muted/20 p-2 text-xs text-muted-foreground">
          This verdict is <strong>informative</strong>: routing never blocks on it, so the plan
          executed regardless (ADR-184). Use the issues below to understand what the validator saw.
        </div>
      )}

      {/* Issues */}
      {data.issues.length > 0 && (
        <div className="space-y-1.5">
          <SubSectionHeader label={`Issues (${data.issues.length})`} borderTop />
          {data.issues.map((issue, index) => (
            <div key={index} className="rounded border border-border/50 bg-muted/30 p-2 text-xs">
              <div className="flex flex-wrap items-center gap-1.5">
                <DebugChip tone={SEVERITY_TONE[issue.severity] ?? 'neutral'}>
                  {issue.severity}
                </DebugChip>
                <span className="font-mono text-[10px] text-muted-foreground">
                  {issue.issue_type}
                </span>
                {issue.step_index !== null && (
                  <span className="font-mono text-[10px] text-muted-foreground">
                    step #{issue.step_index}
                  </span>
                )}
              </div>
              {issue.description && <div className="mt-1">{issue.description}</div>}
              {issue.suggested_fix && (
                <div className="mt-1 italic text-muted-foreground">Fix: {issue.suggested_fix}</div>
              )}
            </div>
          ))}
        </div>
      )}

      {/* Clarification questions */}
      {data.clarification_questions.length > 0 && (
        <div className="space-y-1">
          <SubSectionHeader label="Clarification questions" borderTop />
          {data.clarification_questions.map((question, index) => (
            <div key={index} className="rounded bg-muted/20 p-2 text-xs italic">
              {question}
            </div>
          ))}
        </div>
      )}
    </DebugSection>
  );
});
