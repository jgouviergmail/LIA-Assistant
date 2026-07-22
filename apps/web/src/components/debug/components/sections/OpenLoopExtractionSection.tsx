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
import { AccordionItem, AccordionTrigger, AccordionContent } from '@/components/ui/accordion';
import { cn } from '@/lib/utils';
import { EmptySection, MetricRow } from '../shared';
import type { OpenLoopExtractionMetrics } from '@/types/chat';

export interface OpenLoopExtractionSectionProps {
  data: OpenLoopExtractionMetrics | undefined;
}

/** Direction glyphs: user_owes = outgoing commitment, waiting_on_other = incoming */
const DIRECTION_GLYPH: Record<string, string> = {
  user_owes: '→', // →
  waiting_on_other: '←', // ←
};

export const OpenLoopExtractionSection = React.memo(function OpenLoopExtractionSection({
  data,
}: OpenLoopExtractionSectionProps) {
  if (!data) return <EmptySection value="open-loop-extraction" title="Open Loop Extraction" />;

  const applied = data.opened + data.closed;
  const items = data.items ?? [];

  return (
    <AccordionItem value="open-loop-extraction">
      <AccordionTrigger className="py-2 text-sm">
        <div className="flex items-center gap-2">
          <span>Open Loop Extraction</span>
          <span
            className={cn(
              'text-xs px-1.5 py-0.5 rounded font-medium border',
              applied > 0
                ? 'bg-emerald-500/20 text-emerald-400 border-emerald-500/30'
                : 'bg-muted/50 text-muted-foreground border-border/50'
            )}
          >
            {applied}/{data.items_parsed}
          </span>
          {data.opened > 0 && (
            <span className="text-[9px] px-1 py-0.5 rounded bg-emerald-500/15 text-emerald-400">
              +{data.opened}
            </span>
          )}
          {data.closed > 0 && (
            <span className="text-[9px] px-1 py-0.5 rounded bg-sky-500/15 text-sky-400">
              ✓{data.closed}
            </span>
          )}
          {data.skipped > 0 && (
            <span className="text-[9px] px-1 py-0.5 rounded bg-amber-500/15 text-amber-400">
              ~{data.skipped}
            </span>
          )}
        </div>
      </AccordionTrigger>
      <AccordionContent>
        <div className="space-y-3">
          <div className="grid grid-cols-2 gap-x-4 gap-y-0.5">
            <MetricRow label="Items parsed" value={data.items_parsed} />
            <MetricRow label="Opened" value={data.opened} highlight={data.opened > 0} />
            <MetricRow label="Closed" value={data.closed} highlight={data.closed > 0} />
            <MetricRow label="Skipped" value={data.skipped} />
          </div>

          {items.length > 0 ? (
            <div className="space-y-1.5">
              {items.map((item, index) => (
                <div
                  key={index}
                  className="text-xs p-2 rounded border bg-muted/30 border-border/50"
                >
                  <div className="flex items-center gap-1.5">
                    <span
                      className={cn(
                        'text-[9px] px-1 py-0.5 rounded font-medium uppercase',
                        item.action === 'open'
                          ? 'bg-emerald-500/15 text-emerald-400'
                          : 'bg-sky-500/15 text-sky-400'
                      )}
                    >
                      {item.action}
                    </span>
                    <span className="text-muted-foreground">
                      {DIRECTION_GLYPH[item.direction] ?? ''}
                    </span>
                    <span className="font-medium truncate text-primary">{item.subject}</span>
                  </div>
                  {(item.counterparty || item.due_hint_iso) && (
                    <div className="flex items-center gap-2 mt-0.5 text-muted-foreground">
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
            <div className="text-xs text-muted-foreground italic p-2 bg-muted/20 rounded">
              No commitments detected in this turn.
            </div>
          )}
        </div>
      </AccordionContent>
    </AccordionItem>
  );
});
