/**
 * Context Resolution Section Component
 *
 * Displays conversational context resolution and references.
 */

import React from 'react';
import { Link2 } from 'lucide-react';
import { DebugChip, DebugSection, InfoRow, MetricRow, SubSectionHeader } from '../shared';
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
export const ContextSection = React.memo(function ContextSection({ data }: ContextSectionProps) {
  const isReference = data.is_reference;

  return (
    <DebugSection
      value="context"
      title="Context Resolution"
      icon={Link2}
      badge={isReference ? <DebugChip tone="info">REF</DebugChip> : undefined}
    >
      {/* Context state */}
      <div className="space-y-1">
        <SubSectionHeader label="Conversational state" />
        <MetricRow
          label="Turn type"
          value={data.turn_type === 'initial' ? 'Initial' : data.turn_type}
          highlight
        />
        <MetricRow
          label="Contextual reference"
          value={isReference ? 'Yes' : 'No'}
          highlight
          valueClassName={isReference ? 'text-primary font-medium' : undefined}
        />
      </div>

      {/* Reference source */}
      {isReference && (
        <div className="space-y-1">
          <SubSectionHeader label="Reference source" borderTop />
          <MetricRow
            label="Source turn"
            value={data.source_turn_id !== null ? `#${data.source_turn_id}` : 'N/A'}
            mono
          />
          <MetricRow label="Source domain" value={data.source_domain || 'N/A'} />
        </div>
      )}

      {/* Resolved references */}
      {data.resolved_references && Object.keys(data.resolved_references).length > 0 && (
        <div>
          <SubSectionHeader label="Resolved references" borderTop />
          <div className="space-y-1">
            {Object.entries(data.resolved_references).map(([key, value]) => (
              <div
                key={key}
                className="flex items-center gap-2 rounded border border-border/50 bg-muted/50 p-1.5 text-xs"
              >
                <span className="font-medium text-primary">{key}</span>
                <span className="text-muted-foreground">→</span>
                <span className="truncate font-mono text-[11px] text-foreground/80">{value}</span>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Configuration */}
      {(data.thresholds.confidence_threshold || data.thresholds.active_window_turns) && (
        <div>
          <SubSectionHeader label="Configuration" borderTop />
          {data.thresholds.confidence_threshold && (
            <InfoRow label="Confidence threshold" check={data.thresholds.confidence_threshold} />
          )}
          {data.thresholds.active_window_turns && (
            <InfoRow label="Context window" check={data.thresholds.active_window_turns} />
          )}
        </div>
      )}
    </DebugSection>
  );
});
