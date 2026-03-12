/**
 * Context Resolution Section Component
 *
 * Displays conversational context resolution and references.
 */

import React from 'react';
import {
  AccordionItem,
  AccordionTrigger,
  AccordionContent,
} from '@/components/ui/accordion';
import {
  MetricRow,
  InfoRow,
} from '../shared';
import type { DebugMetrics } from '@/types/chat';

export interface ContextSectionProps {
  /** Context resolution metrics */
  data: DebugMetrics['context_resolution'];
}

/**
 * Context Resolution Section
 *
 * Clearly displays:
 * - The conversational turn type
 * - Whether the query references a previous exchange
 * - Resolved references (e.g., "the 2nd" -> contact_id)
 */
export const ContextSection = React.memo(function ContextSection({
  data,
}: ContextSectionProps) {
  const isReference = data.is_reference;

  return (
    <AccordionItem value="context">
      <AccordionTrigger className="py-2 text-sm">
        <div className="flex items-center gap-2">
          <span>Context Resolution</span>
          {isReference && (
            <span className="text-xs bg-primary/20 text-primary px-1.5 py-0.5 rounded font-medium border border-primary/30">
              REF
            </span>
          )}
        </div>
      </AccordionTrigger>
      <AccordionContent>
        <div className="space-y-3">
          {/* Context state */}
          <div className="space-y-1">
            <div className="text-xs text-muted-foreground font-medium mb-1">
              État conversationnel
            </div>
            <MetricRow
              label="Type de tour"
              value={data.turn_type === 'initial' ? 'Initial' : data.turn_type}
              highlight
            />
            <MetricRow
              label="Référence contextuelle"
              value={isReference ? 'Oui' : 'Non'}
              highlight
              valueClassName={isReference ? 'text-primary font-medium' : undefined}
            />
          </div>

          {/* Reference source */}
          {isReference && (
            <div className="border-t border-border/50 pt-2 space-y-1">
              <div className="text-xs text-muted-foreground font-medium mb-1">
                Source de la référence
              </div>
              <MetricRow
                label="Tour source"
                value={data.source_turn_id !== null ? `#${data.source_turn_id}` : 'N/A'}
                mono
              />
              <MetricRow
                label="Domaine source"
                value={data.source_domain || 'N/A'}
              />
            </div>
          )}

          {/* Resolved references */}
          {data.resolved_references && Object.keys(data.resolved_references).length > 0 && (
            <div className="border-t border-border/50 pt-2">
              <div className="text-xs text-muted-foreground font-medium mb-1.5">
                Références résolues
              </div>
              <div className="space-y-1">
                {Object.entries(data.resolved_references).map(([key, value]) => (
                  <div
                    key={key}
                    className="flex items-center gap-2 text-xs p-1.5 bg-muted/50 rounded border border-border/50"
                  >
                    <span className="text-primary font-medium">{key}</span>
                    <span className="text-muted-foreground/50">→</span>
                    <span className="font-mono text-[11px] text-foreground/80 truncate">
                      {value}
                    </span>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Configuration */}
          {(data.thresholds.confidence_threshold || data.thresholds.active_window_turns) && (
            <div className="border-t border-border/50 pt-2">
              <div className="text-xs text-muted-foreground font-medium mb-1.5">
                Configuration
              </div>
              {data.thresholds.confidence_threshold && (
                <InfoRow
                  label="Seuil de confiance"
                  check={data.thresholds.confidence_threshold}
                />
              )}
              {data.thresholds.active_window_turns && (
                <InfoRow
                  label="Fenêtre de contexte"
                  check={data.thresholds.active_window_turns}
                />
              )}
            </div>
          )}
        </div>
      </AccordionContent>
    </AccordionItem>
  );
});
