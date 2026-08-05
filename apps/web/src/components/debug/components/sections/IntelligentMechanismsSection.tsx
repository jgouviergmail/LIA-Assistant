/**
 * Intelligent Mechanisms Section Component
 *
 * Displays intelligent mechanisms applied during query processing.
 *
 * v3.1: LLM Query Analysis is the primary mechanism
 */

import React from 'react';
import { Sparkles } from 'lucide-react';
import { DebugChip, DebugSection, EmptySection, MetricRow } from '../shared';
import { formatPercent } from '../../utils/formatters';
import type { IntelligentMechanisms } from '@/types/chat';

export interface IntelligentMechanismsSectionProps {
  /** Intelligent mechanisms data */
  data: IntelligentMechanisms | undefined;
}

/**
 * Intelligent Mechanisms Section
 *
 * Displays v3.1 mechanisms with a consistent and clean design.
 */
export const IntelligentMechanismsSection = React.memo(function IntelligentMechanismsSection({
  data,
}: IntelligentMechanismsSectionProps) {
  const mechanismsApplied = data ? Object.values(data).filter(m => m?.applied).length : 0;
  if (!data || mechanismsApplied === 0) {
    return (
      <EmptySection
        value="mechanisms"
        title="Intelligent Mechanisms"
        icon={Sparkles}
        message="No intelligent mechanism was applied to this query."
      />
    );
  }

  return (
    <DebugSection
      value="mechanisms"
      title="Intelligent Mechanisms"
      icon={Sparkles}
      badge={
        <DebugChip tone="neutral">
          {mechanismsApplied} active
        </DebugChip>
      }
    >
      {/* LLM Query Analysis - v3.1 Primary Mechanism */}
      {data.llm_query_analysis?.applied && (
        <div className="border-l-2 border-primary/50 pl-3">
          <div className="mb-2 flex items-center gap-2">
            <span className="text-xs font-semibold text-foreground">LLM Query Analysis</span>
            <DebugChip tone="info">v3.1</DebugChip>
          </div>
          <div className="space-y-2 text-xs">
            {/* Intent mapping */}
            <div className="flex flex-wrap items-center gap-2">
              <span className="text-muted-foreground">Intent:</span>
              <span className="rounded border border-border bg-muted px-1.5 py-0.5">
                {data.llm_query_analysis.intent}
              </span>
              <span className="text-muted-foreground">→</span>
              <span className="rounded border border-primary/30 bg-primary/20 px-1.5 py-0.5 font-medium text-primary">
                {data.llm_query_analysis.mapped_intent}
              </span>
              <span className="ml-2 text-muted-foreground">
                ({formatPercent(data.llm_query_analysis.confidence)})
              </span>
            </div>

            {/* Domains */}
            <div className="flex flex-wrap items-center gap-2">
              <span className="text-muted-foreground">Domains:</span>
              {data.llm_query_analysis.primary_domain && (
                <span className="rounded bg-primary px-1.5 py-0.5 font-medium text-primary-foreground">
                  {data.llm_query_analysis.primary_domain}
                </span>
              )}
              {(data.llm_query_analysis.secondary_domains ?? []).map(domain => (
                <span key={domain} className="rounded border border-border bg-muted px-1.5 py-0.5">
                  {domain}
                </span>
              ))}
              {!data.llm_query_analysis.primary_domain &&
                (data.llm_query_analysis.secondary_domains ?? []).length === 0 && (
                  <span className="italic text-muted-foreground">none</span>
                )}
            </div>

            {/* English Translation */}
            <div>
              <span className="text-muted-foreground">EN: </span>
              <span className="italic text-foreground/80">
                {data.llm_query_analysis.english_query}
              </span>
            </div>

            {/* Reasoning */}
            {data.llm_query_analysis.reasoning && (
              <div className="rounded border border-border/50 bg-muted/30 p-2 italic text-muted-foreground">
                &quot;{data.llm_query_analysis.reasoning}&quot;
              </div>
            )}
          </div>
        </div>
      )}

      {/* Memory Resolution */}
      {data.memory_resolution?.applied && (
        <div className="border-l-2 border-border pl-3">
          <div className="mb-2 text-xs font-semibold text-foreground">Memory Resolution</div>
          <div className="space-y-2 text-xs">
            {/* v3.1: Resolved References (prioritized when available) */}
            {(data.memory_resolution.resolved_references ?? []).map((ref, i) => (
              <div
                key={i}
                className="flex items-center gap-2 rounded border border-border/50 bg-muted/30 p-1.5 font-mono"
              >
                <span className="text-muted-foreground">&quot;{ref.original}&quot;</span>
                <span className="text-muted-foreground">→</span>
                <span className="font-medium text-foreground">&quot;{ref.resolved}&quot;</span>
                <span className="text-[10px] text-muted-foreground">({ref.type})</span>
              </div>
            ))}
            {/* v3.0 legacy fallback: only show if resolved_references empty/missing */}
            {(data.memory_resolution.resolved_references ?? []).length === 0 &&
              data.memory_resolution.mappings &&
              Object.keys(data.memory_resolution.mappings).length > 0 &&
              Object.entries(data.memory_resolution.mappings).map(([key, value]) => (
                <div
                  key={key}
                  className="flex items-center gap-2 rounded border border-border/50 bg-muted/30 p-1.5 font-mono"
                >
                  <span className="text-muted-foreground">&quot;{key}&quot;</span>
                  <span className="text-muted-foreground">→</span>
                  <span className="font-medium text-foreground">&quot;{value}&quot;</span>
                  <span className="text-[10px] text-muted-foreground">(v3.0)</span>
                </div>
              ))}
          </div>
        </div>
      )}

      {/* Semantic Expansion */}
      {data.semantic_expansion?.applied && (
        <div className="border-l-2 border-border pl-3">
          <div className="mb-2 text-xs font-semibold text-foreground">Semantic Expansion</div>
          <div className="space-y-1 text-xs">
            <div className="flex flex-wrap items-center gap-2">
              <span className="text-muted-foreground">Original:</span>
              <span className="rounded border border-border bg-muted px-1.5 py-0.5">
                {data.semantic_expansion.original_domains.join(', ')}
              </span>
            </div>
            {data.semantic_expansion.added_domains.length > 0 && (
              <div className="flex flex-wrap items-center gap-2">
                <span className="text-muted-foreground">Added:</span>
                {data.semantic_expansion.added_domains.map(domain => (
                  <span
                    key={domain}
                    className="rounded border border-primary/30 bg-primary/20 px-1.5 py-0.5 text-primary"
                  >
                    + {domain}
                  </span>
                ))}
              </div>
            )}
            {data.semantic_expansion.reasons.length > 0 && (
              <div className="italic text-muted-foreground">
                Reason: {data.semantic_expansion.reasons[0]}
              </div>
            )}
          </div>
        </div>
      )}

      {/* Chat Override */}
      {data.chat_override?.applied && (
        <div className="border-l-2 border-border pl-3">
          <div className="mb-2 text-xs font-semibold text-foreground">Chat Override</div>
          <div className="space-y-1 text-xs">
            <div className="rounded border border-border/50 bg-muted/30 p-2 italic text-muted-foreground">
              {data.chat_override.reason}
            </div>
            {data.chat_override.original_domains.length > 0 && (
              <div className="text-muted-foreground line-through">
                Ignored domains: {data.chat_override.original_domains.join(', ')}
              </div>
            )}
            <MetricRow
              label="Override threshold"
              value={formatPercent(data.chat_override.override_threshold)}
            />
          </div>
        </div>
      )}

      {/* Semantic Pivot - legacy v3.0, rare now */}
      {data.semantic_pivot?.applied && (
        <div className="border-l-2 border-border pl-3">
          <div className="mb-2 text-xs font-semibold text-foreground">Semantic Pivot (legacy)</div>
          <div className="space-y-1 text-xs">
            <MetricRow label="Source language" value={data.semantic_pivot.source_language} />
            <div className="italic text-muted-foreground">
              {data.semantic_pivot.original_query} → {data.semantic_pivot.translated_query}
            </div>
          </div>
        </div>
      )}
    </DebugSection>
  );
});
