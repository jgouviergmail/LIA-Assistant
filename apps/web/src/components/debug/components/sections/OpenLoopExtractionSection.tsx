/**
 * Open Loop Extraction Section Component
 *
 * Displays the commitments the background extraction (ADR-139) started
 * tracking or closed after this turn: what the LLM proposed (items) and
 * what the deterministic guards actually applied (opened/closed/skipped).
 *
 * Sibling of JournalExtractionSection in the Background Extraction group.
 */

import React from 'react';
import { ListTodo } from 'lucide-react';
import { DebugChip, DebugSection, EmptySection, MetricRow } from '../shared';
import { ExtractionLLMFooter } from './MemoryDetectionSection';
import type { OpenLoopExtractionMetrics } from '@/types/chat';

export interface OpenLoopExtractionSectionProps {
  data: OpenLoopExtractionMetrics | undefined;
}

/** Direction glyphs: user_owes = outgoing commitment, waiting_on_other = incoming */
const DIRECTION_GLYPH: Record<string, string> = {
  user_owes: '→',
  waiting_on_other: '←',
};

export const OpenLoopExtractionSection = React.memo(function OpenLoopExtractionSection({
  data,
}: OpenLoopExtractionSectionProps) {
  if (!data) {
    return (
      <EmptySection
        value="open-loop-extraction"
        title="Open Loop Extraction"
        icon={ListTodo}
        message="No open-loop extraction ran on this turn."
      />
    );
  }

  const applied = data.opened + data.closed;
  const items = data.items ?? [];

  return (
    <DebugSection
      value="open-loop-extraction"
      title="Open Loop Extraction"
      icon={ListTodo}
      badge={
        <>
          <DebugChip tone={applied > 0 ? 'success' : 'neutral'}>
            {applied}/{data.items_parsed}
          </DebugChip>
          {data.opened > 0 && <DebugChip tone="success">+{data.opened}</DebugChip>}
          {data.closed > 0 && <DebugChip tone="info">✓{data.closed}</DebugChip>}
          {data.skipped > 0 && <DebugChip tone="warning">~{data.skipped}</DebugChip>}
        </>
      }
    >
      <div className="grid grid-cols-2 gap-x-4 gap-y-0.5">
        <MetricRow label="Items parsed" value={data.items_parsed} />
        <MetricRow label="Opened" value={data.opened} highlight={data.opened > 0} />
        <MetricRow label="Closed" value={data.closed} highlight={data.closed > 0} />
        <MetricRow label="Skipped" value={data.skipped} />
      </div>

      {items.length > 0 ? (
        <div className="space-y-1.5">
          {items.map((item, index) => (
            <div key={index} className="rounded border border-border/50 bg-muted/30 p-2 text-xs">
              <div className="flex items-center gap-1.5">
                <DebugChip tone={item.action === 'open' ? 'success' : 'info'}>
                  {item.action}
                </DebugChip>
                <span className="text-muted-foreground">
                  {DIRECTION_GLYPH[item.direction] ?? ''}
                </span>
                <span className="truncate font-medium text-primary">{item.subject}</span>
              </div>
              {(item.counterparty || item.due_hint_iso) && (
                <div className="mt-0.5 flex items-center gap-2 text-muted-foreground">
                  {item.counterparty && <span>{item.counterparty}</span>}
                  {item.due_hint_iso && (
                    <span className="font-mono text-[10px]">{item.due_hint_iso}</span>
                  )}
                </div>
              )}
            </div>
          ))}
        </div>
      ) : (
        <div className="rounded bg-muted/20 p-2 text-xs italic text-muted-foreground">
          No commitments detected in this turn.
        </div>
      )}

      {data.llm_metadata && <ExtractionLLMFooter metadata={data.llm_metadata} />}
    </DebugSection>
  );
});
