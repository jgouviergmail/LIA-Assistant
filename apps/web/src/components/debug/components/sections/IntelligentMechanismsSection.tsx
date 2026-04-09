/**
 * Intelligent Mechanisms Section Component
 *
 * Displays intelligent mechanisms applied during query processing.
 *
 * v3.1: LLM Query Analysis is the primary mechanism
 */

import React from 'react';
import { AccordionItem, AccordionTrigger, AccordionContent } from '@/components/ui/accordion';
import { EmptySection, MetricRow } from '../shared';
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
  if (!data) return <EmptySection value="mechanisms" title="Intelligent Mechanisms" />;

  const mechanismsApplied = Object.values(data).filter(m => m?.applied).length;
  if (mechanismsApplied === 0) return <EmptySection value="mechanisms" title="Intelligent Mechanisms" />;

  return (
    <AccordionItem value="mechanisms">
      <AccordionTrigger className="py-2 text-sm">
        <div className="flex items-center gap-2">
          <span>Intelligent Mechanisms</span>
          <span className="text-xs bg-muted text-muted-foreground px-2 py-0.5 rounded border border-border">
            {mechanismsApplied} actif{mechanismsApplied > 1 ? 's' : ''}
          </span>
        </div>
      </AccordionTrigger>
      <AccordionContent>
        <div className="space-y-3">
          {/* LLM Query Analysis - v3.1 Primary Mechanism */}
          {data.llm_query_analysis?.applied && (
            <div className="border-l-2 border-primary/50 pl-3">
              <div className="flex items-center gap-2 mb-2">
                <span className="text-xs font-semibold text-foreground">LLM Query Analysis</span>
                <span className="text-[10px] bg-primary/20 text-primary px-1.5 py-0.5 rounded border border-primary/30">
                  v3.1
                </span>
              </div>
              <div className="space-y-2 text-xs">
                {/* Intent mapping */}
                <div className="flex items-center gap-2 flex-wrap">
                  <span className="text-muted-foreground">Intent:</span>
                  <span className="bg-muted px-1.5 py-0.5 rounded border border-border">
                    {data.llm_query_analysis.intent}
                  </span>
                  <span className="text-muted-foreground">→</span>
                  <span className="bg-primary/20 text-primary px-1.5 py-0.5 rounded border border-primary/30 font-medium">
                    {data.llm_query_analysis.mapped_intent}
                  </span>
                  <span className="text-muted-foreground ml-2">
                    ({formatPercent(data.llm_query_analysis.confidence)})
                  </span>
                </div>

                {/* Domains */}
                <div className="flex items-center gap-2 flex-wrap">
                  <span className="text-muted-foreground">Domaines:</span>
                  {data.llm_query_analysis.primary_domain && (
                    <span className="bg-primary text-primary-foreground px-1.5 py-0.5 rounded font-medium">
                      {data.llm_query_analysis.primary_domain}
                    </span>
                  )}
                  {(data.llm_query_analysis.secondary_domains ?? []).map(domain => (
                    <span
                      key={domain}
                      className="bg-muted px-1.5 py-0.5 rounded border border-border"
                    >
                      {domain}
                    </span>
                  ))}
                  {!data.llm_query_analysis.primary_domain &&
                    (data.llm_query_analysis.secondary_domains ?? []).length === 0 && (
                      <span className="text-muted-foreground italic">aucun</span>
                    )}
                </div>

                {/* English Translation */}
                <div>
                  <span className="text-muted-foreground">EN: </span>
                  <span className="text-foreground/80 italic">
                    {data.llm_query_analysis.english_query}
                  </span>
                </div>

                {/* Reasoning */}
                {data.llm_query_analysis.reasoning && (
                  <div className="text-muted-foreground italic bg-muted/30 p-2 rounded border border-border/50">
                    &quot;{data.llm_query_analysis.reasoning}&quot;
                  </div>
                )}
              </div>
            </div>
          )}

          {/* Memory Resolution */}
          {data.memory_resolution?.applied && (
            <div className="border-l-2 border-border pl-3">
              <div className="text-xs font-semibold text-foreground mb-2">Memory Resolution</div>
              <div className="space-y-2 text-xs">
                {/* v3.1: Resolved References (prioritized when available) */}
                {(data.memory_resolution.resolved_references ?? []).map((ref, i) => (
                  <div
                    key={i}
                    className="flex items-center gap-2 font-mono bg-muted/30 p-1.5 rounded border border-border/50"
                  >
                    <span className="text-muted-foreground">&quot;{ref.original}&quot;</span>
                    <span className="text-muted-foreground">→</span>
                    <span className="text-foreground font-medium">&quot;{ref.resolved}&quot;</span>
                    <span className="text-muted-foreground text-[10px]">({ref.type})</span>
                  </div>
                ))}
                {/* v3.0 legacy fallback: only show if resolved_references empty/missing */}
                {(data.memory_resolution.resolved_references ?? []).length === 0 &&
                  data.memory_resolution.mappings &&
                  Object.keys(data.memory_resolution.mappings).length > 0 &&
                  Object.entries(data.memory_resolution.mappings).map(([key, value]) => (
                    <div
                      key={key}
                      className="flex items-center gap-2 font-mono bg-muted/30 p-1.5 rounded border border-border/50"
                    >
                      <span className="text-muted-foreground">&quot;{key}&quot;</span>
                      <span className="text-muted-foreground">→</span>
                      <span className="text-foreground font-medium">&quot;{value}&quot;</span>
                      <span className="text-muted-foreground text-[10px]">(v3.0)</span>
                    </div>
                  ))}
              </div>
            </div>
          )}

          {/* Semantic Expansion */}
          {data.semantic_expansion?.applied && (
            <div className="border-l-2 border-border pl-3">
              <div className="text-xs font-semibold text-foreground mb-2">Semantic Expansion</div>
              <div className="space-y-1 text-xs">
                <div className="flex items-center gap-2 flex-wrap">
                  <span className="text-muted-foreground">Original:</span>
                  <span className="bg-muted px-1.5 py-0.5 rounded border border-border">
                    {data.semantic_expansion.original_domains.join(', ')}
                  </span>
                </div>
                {data.semantic_expansion.added_domains.length > 0 && (
                  <div className="flex items-center gap-2 flex-wrap">
                    <span className="text-muted-foreground">Ajoutés:</span>
                    {data.semantic_expansion.added_domains.map(domain => (
                      <span
                        key={domain}
                        className="bg-primary/20 text-primary px-1.5 py-0.5 rounded border border-primary/30"
                      >
                        + {domain}
                      </span>
                    ))}
                  </div>
                )}
                {data.semantic_expansion.reasons.length > 0 && (
                  <div className="text-muted-foreground italic">
                    Raison: {data.semantic_expansion.reasons[0]}
                  </div>
                )}
              </div>
            </div>
          )}

          {/* Chat Override */}
          {data.chat_override?.applied && (
            <div className="border-l-2 border-border pl-3">
              <div className="text-xs font-semibold text-foreground mb-2">Chat Override</div>
              <div className="space-y-1 text-xs">
                <div className="text-muted-foreground italic bg-muted/30 p-2 rounded border border-border/50">
                  {data.chat_override.reason}
                </div>
                {data.chat_override.original_domains.length > 0 && (
                  <div className="text-muted-foreground line-through">
                    Domaines ignorés: {data.chat_override.original_domains.join(', ')}
                  </div>
                )}
                <MetricRow
                  label="Seuil override"
                  value={formatPercent(data.chat_override.override_threshold)}
                />
              </div>
            </div>
          )}

          {/* Semantic Pivot - legacy v3.0, rare now */}
          {data.semantic_pivot?.applied && (
            <div className="border-l-2 border-border pl-3">
              <div className="text-xs font-semibold text-foreground mb-2">
                Semantic Pivot (legacy)
              </div>
              <div className="space-y-1 text-xs">
                <MetricRow label="Langue source" value={data.semantic_pivot.source_language} />
                <div className="text-muted-foreground italic">
                  {data.semantic_pivot.original_query} → {data.semantic_pivot.translated_query}
                </div>
              </div>
            </div>
          )}
        </div>
      </AccordionContent>
    </AccordionItem>
  );
});
