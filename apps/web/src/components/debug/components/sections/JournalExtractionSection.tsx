/**
 * Journal Extraction Section Component
 *
 * Displays journal entries created, updated, or deleted by the background
 * extraction pipeline. Separated from journal injection for clarity.
 *
 * Shows action type (CREATE/UPDATE/DELETE), theme, title, mood for each action.
 */

import React from 'react';
import { AccordionItem, AccordionTrigger, AccordionContent } from '@/components/ui/accordion';
import { cn } from '@/lib/utils';
import { ActionBadge, EmptySection, MetricRow } from '../shared';
import type { JournalExtractionMetrics } from '@/types/chat';

export interface JournalExtractionSectionProps {
  data: JournalExtractionMetrics | undefined;
}

/** Theme emoji mapping */
const THEME_EMOJI: Record<string, string> = {
  self_reflection: '\u{1F6AA}',
  user_observations: '\u{1F441}\uFE0F',
  ideas_analyses: '\u{1F4A1}',
  learnings: '\u{1F4DA}',
};

/** Mood emoji mapping */
const MOOD_EMOJI: Record<string, string> = {
  reflective: '\u{1F4AD}',
  curious: '\u{1F914}',
  satisfied: '\u{1F60A}',
  concerned: '\u{1F61F}',
  inspired: '\u{1F4A1}',
};

export const JournalExtractionSection = React.memo(function JournalExtractionSection({
  data,
}: JournalExtractionSectionProps) {
  if (!data) return <EmptySection value="journal-extraction" title="Journal Extraction" />;

  const hasActions = data.actions_applied > 0;
  const entries = data.entries ?? [];

  // Count by action type
  const creates = entries.filter(e => e.action === 'create').length;
  const updates = entries.filter(e => e.action === 'update').length;
  const deletes = entries.filter(e => e.action === 'delete').length;

  return (
    <AccordionItem value="journal-extraction">
      <AccordionTrigger className="py-2 text-sm">
        <div className="flex items-center gap-2">
          <span>Journal Extraction</span>
          <span
            className={cn(
              'text-xs px-1.5 py-0.5 rounded font-medium border',
              hasActions
                ? 'bg-emerald-500/20 text-emerald-400 border-emerald-500/30'
                : 'bg-muted/50 text-muted-foreground border-border/50'
            )}
          >
            {data.actions_applied}/{data.actions_parsed}
          </span>
          {creates > 0 && (
            <span className="text-[9px] px-1 py-0.5 rounded bg-emerald-500/15 text-emerald-400">
              +{creates}
            </span>
          )}
          {updates > 0 && (
            <span className="text-[9px] px-1 py-0.5 rounded bg-amber-500/15 text-amber-400">
              ~{updates}
            </span>
          )}
          {deletes > 0 && (
            <span className="text-[9px] px-1 py-0.5 rounded bg-red-500/15 text-red-400">
              -{deletes}
            </span>
          )}
        </div>
      </AccordionTrigger>
      <AccordionContent>
        <div className="space-y-3">
          <div className="grid grid-cols-2 gap-x-4 gap-y-0.5">
            <MetricRow label="Actions parsed" value={data.actions_parsed} />
            <MetricRow
              label="Actions applied"
              value={data.actions_applied}
              highlight={hasActions}
            />
          </div>

          {entries.length > 0 ? (
            <div className="space-y-1.5">
              {entries.map((entry, index) => {
                const themeEmoji = entry.theme ? (THEME_EMOJI[entry.theme] ?? '') : '';
                const moodEmoji = entry.mood ? (MOOD_EMOJI[entry.mood] ?? '') : '';

                return (
                  <div
                    key={index}
                    className="text-xs p-2 rounded border bg-muted/30 border-border/50 cursor-help"
                    title={`${entry.full_title ?? entry.title ?? ''}\n\n${entry.content ?? ''}`}
                  >
                    <div className="flex items-center gap-1.5">
                      <ActionBadge action={entry.action} />
                      {themeEmoji && <span>{themeEmoji}</span>}
                      <span
                        className={cn(
                          'font-medium truncate',
                          entry.action === 'delete'
                            ? 'text-red-400/60 line-through'
                            : 'text-primary'
                        )}
                      >
                        {entry.full_title ?? entry.title ?? entry.entry_id?.slice(0, 8) ?? '—'}
                      </span>
                      {moodEmoji && <span className="text-muted-foreground">{moodEmoji}</span>}
                    </div>
                    {entry.theme && (
                      <div className="flex items-center gap-2 mt-0.5 text-muted-foreground">
                        <span>{entry.theme.replace('_', ' ')}</span>
                        {entry.entry_id && (
                          <span className="font-mono text-[10px]">
                            {entry.entry_id.slice(0, 8)}
                          </span>
                        )}
                      </div>
                    )}
                  </div>
                );
              })}
            </div>
          ) : (
            <div className="text-xs text-muted-foreground italic p-2 bg-muted/20 rounded">
              No journal actions for this message.
            </div>
          )}
        </div>
      </AccordionContent>
    </AccordionItem>
  );
});
