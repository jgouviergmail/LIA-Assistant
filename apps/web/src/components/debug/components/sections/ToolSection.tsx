/**
 * Tool Selection Section Component
 *
 * Displays the tools selected to execute the query.
 * Handles the case where the query routes to chat (no tools).
 *
 * v3.1 LLM-based: The planner selects tools directly.
 */

import React from 'react';
import { AccordionItem, AccordionTrigger, AccordionContent } from '@/components/ui/accordion';
import { validateToolScores } from '../../validation/validators';
import {
  MetricRow,
  ThresholdRow,
  InfoRow,
  ScoresList,
  ToolMatchRow,
  SectionBadge,
} from '../shared';
import {
  ERROR_SECTION_CLASSES,
  INFO_SECTION_CLASSES,
  DEFAULT_THRESHOLDS,
} from '../../utils/constants';
import { formatPercent } from '../../utils/formatters';
import type { DebugMetrics } from '@/types/chat';

export interface ToolSectionProps {
  /** Tool selection metrics (can be undefined if chat) */
  data: DebugMetrics['tool_selection'];
}

/**
 * Section Tool Selection
 *
 * v3.1 LLM-based:
 * - The planner selects tools via LLM
 * - Direct confidence scores (no more softmax/calibration)
 */
export const ToolSection = React.memo(function ToolSection({ data }: ToolSectionProps) {
  // Case: no selection (routed to chat)
  if (!data) {
    return (
      <AccordionItem value="tools">
        <AccordionTrigger className="py-2 text-sm">
          <div className="flex items-center gap-2">
            <span>Tool Selection</span>
            <SectionBadge passed={false} label="N/A" />
          </div>
        </AccordionTrigger>
        <AccordionContent>
          <div className={INFO_SECTION_CLASSES}>
            <strong>Non exécuté :</strong> La requête a été routée vers le chat (conversation
            simple) ou aucun outil ne correspond.
          </div>
        </AccordionContent>
      </AccordionItem>
    );
  }

  const scoresValidation = validateToolScores(data);
  const primaryMin = data.thresholds.primary_min?.value ?? DEFAULT_THRESHOLDS.tool.primary_min;
  const passed = data.top_score >= primaryMin;

  return (
    <AccordionItem value="tools">
      <AccordionTrigger className="py-2 text-sm">
        <div className="flex items-center gap-2">
          <span>Tool Selection</span>
          <SectionBadge passed={passed} value={data.top_score} />
        </div>
      </AccordionTrigger>
      <AccordionContent>
        <div className="space-y-3">
          {/* Selection summary */}
          <div className="space-y-1">
            <div className="text-xs text-muted-foreground font-medium mb-1">
              Résultat de la sélection
            </div>
            <MetricRow
              label="Nombre d'outils"
              value={(data.selected_tools ?? []).length}
              highlight
            />
            <MetricRow
              label="Confiance"
              value={formatPercent(data.top_score)}
              highlight
              valueClassName={passed ? 'text-green-400 font-semibold' : 'text-red-400'}
            />
            <MetricRow label="Incertitude" value={data.has_uncertainty ? 'Oui' : 'Non'} />
          </div>

          {/* Detailed tools list */}
          {(data.selected_tools ?? []).length > 0 && (
            <div className="border-t pt-2">
              <div className="text-xs text-muted-foreground font-medium mb-1.5">
                Outils sélectionnés
              </div>
              <div className="space-y-1">
                {(data.selected_tools ?? []).map((tool, index) => (
                  <ToolMatchRow key={`${tool.tool_name}-${index}`} tool={tool} />
                ))}
              </div>
            </div>
          )}

          {/* Configuration */}
          <div className="border-t pt-2">
            <div className="text-xs text-muted-foreground font-medium mb-1.5">Seuils</div>
            {data.thresholds.primary_min && (
              <ThresholdRow label="Confiance minimum" check={data.thresholds.primary_min} />
            )}
            {data.thresholds.max_tools && (
              <InfoRow label="Maximum d'outils" check={data.thresholds.max_tools} />
            )}
          </div>

          {/* Score details */}
          {scoresValidation.success && (
            <div className="border-t pt-2">
              <ScoresList
                scores={scoresValidation.data!}
                label="Confiance par outil"
                passThreshold={primaryMin}
              />
            </div>
          )}

          {/* Error if no scores */}
          {!scoresValidation.success && scoresValidation.errors?.[0] !== 'SECTION_ABSENT' && (
            <div className={ERROR_SECTION_CLASSES}>
              <strong>Erreur :</strong> {scoresValidation.errors?.[0] || 'Aucun score disponible'}
            </div>
          )}
        </div>
      </AccordionContent>
    </AccordionItem>
  );
});
