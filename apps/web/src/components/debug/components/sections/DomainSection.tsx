/**
 * Domain Selection Section Component
 *
 * Displays the functional domains identified for the query.
 * v3.1: LLM-based selection via QueryAnalyzerService.
 */

import React from 'react';
import { AccordionItem, AccordionTrigger, AccordionContent } from '@/components/ui/accordion';
import { validateDomainScores } from '../../validation/validators';
import { MetricRow, ThresholdRow, InfoRow, ScoresList, SectionBadge } from '../shared';
import { ERROR_SECTION_CLASSES, DEFAULT_THRESHOLDS } from '../../utils/constants';
import { formatPercent } from '../../utils/formatters';
import type { DebugMetrics, IntelligentMechanisms } from '@/types/chat';

export interface DomainSectionProps {
  /** Domain selection metrics */
  data: DebugMetrics['domain_selection'];
  /** v3.1: Intelligent mechanisms (for LLM badge) */
  mechanisms?: IntelligentMechanisms;
}

/**
 * Section Domain Selection
 *
 * Architecture v3.1 LLM-based:
 * - The LLM analyzes the query and selects relevant domains
 * - A single confidence score is assigned to all selected domains
 * - No more softmax calibration (legacy embeddings concept)
 */
export const DomainSection = React.memo(function DomainSection({
  data,
  mechanisms,
}: DomainSectionProps) {
  const scoresValidation = validateDomainScores(data);
  const primaryMin = data.thresholds.primary_min?.value ?? DEFAULT_THRESHOLDS.domain.primary_min;
  const passed = data.top_score >= primaryMin;
  const isLLMBased = mechanisms?.llm_query_analysis?.applied ?? false;
  const llmReasoning = mechanisms?.llm_query_analysis?.reasoning;

  return (
    <AccordionItem value="domain">
      <AccordionTrigger className="py-2 text-sm">
        <div className="flex items-center gap-2">
          <span>Domain Selection</span>
          {isLLMBased && (
            <span className="text-xs bg-primary/20 text-primary px-1.5 py-0.5 rounded font-medium border border-primary/30">
              LLM
            </span>
          )}
          <SectionBadge passed={passed} value={data.top_score} />
        </div>
      </AccordionTrigger>
      <AccordionContent>
        <div className="space-y-3">
          {/* Selected domains */}
          <div className="space-y-1">
            <div className="text-xs text-muted-foreground font-medium mb-1">
              Résultat de la sélection
            </div>
            <MetricRow
              label="Domaines actifs"
              value={data.selected_domains.join(', ') || 'Aucun'}
              highlight
            />
            <MetricRow label="Domaine principal" value={data.primary_domain} highlight />
            <MetricRow
              label="Confiance LLM"
              value={formatPercent(data.top_score)}
              highlight
              valueClassName={passed ? 'text-green-400 font-semibold' : 'text-red-400'}
            />
          </div>

          {/* LLM reasoning (if available) */}
          {llmReasoning && (
            <div className="border-t pt-2">
              <div className="text-xs text-muted-foreground font-medium mb-1">Raisonnement LLM</div>
              <div className="text-xs bg-muted/30 p-2 rounded border border-border/50 text-foreground/80 italic">
                {llmReasoning}
              </div>
            </div>
          )}

          {/* Configuration */}
          <div className="border-t pt-2">
            <div className="text-xs text-muted-foreground font-medium mb-1.5">Seuils</div>
            {data.thresholds.primary_min && (
              <ThresholdRow label="Confiance minimum" check={data.thresholds.primary_min} />
            )}
            {data.thresholds.max_domains && (
              <InfoRow label="Maximum de domaines" check={data.thresholds.max_domains} />
            )}
          </div>

          {/* Score details per domain */}
          <div className="border-t pt-2">
            {scoresValidation.success ? (
              <ScoresList
                scores={scoresValidation.data!}
                label="Confiance par domaine"
                passThreshold={primaryMin}
                selectedItems={data.selected_domains}
              />
            ) : (
              <div className={ERROR_SECTION_CLASSES}>
                <strong>Erreur :</strong> {scoresValidation.errors?.[0] || 'Aucun score disponible'}
              </div>
            )}
          </div>
        </div>
      </AccordionContent>
    </AccordionItem>
  );
});
