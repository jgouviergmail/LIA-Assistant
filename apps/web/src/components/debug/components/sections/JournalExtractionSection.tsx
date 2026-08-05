/**
 * Journal Extraction Section Component
 *
 * Displays journal entries created, updated, or deleted by the background
 * extraction pipeline. Separated from journal injection for clarity.
 *
 * Shows action type (CREATE/UPDATE/DELETE), theme, title, mood for each action.
 */

import React from 'react';
import { NotebookText } from 'lucide-react';
import { cn } from '@/lib/utils';
import { ActionBadge, DebugChip, DebugSection, EmptySection, MetricRow } from '../shared';
import { TONE_TEXT } from '../../utils/tones';
import type { JournalExtractionMetrics } from '@/types/chat';

export interface JournalExtractionSectionProps {
  data: JournalExtractionMetrics | undefined;
}

/** Theme emoji mapping */
const THEME_EMOJI: Record<string, string> = {
  self_reflection: '\u{1F6AA}',
  user_observations: '\u{1F441}️',
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
  if (!data) {
    return (
      <EmptySection
        value="journal-extraction"
        title="Journal Extraction"
        icon={NotebookText}
        message="No journal extraction ran on this turn."
      />
    );
  }

  const hasActions = data.actions_applied > 0;
  const entries = data.entries ?? [];

  // Count by action type
  const creates = entries.filter(e => e.action === 'create').length;
  const updates = entries.filter(e => e.action === 'update').length;
  const deletes = entries.filter(e => e.action === 'delete').length;

  return (
    <DebugSection
      value="journal-extraction"
      title="Journal Extraction"
      icon={NotebookText}
      badge={
        <>
          <DebugChip tone={hasActions ? 'success' : 'neutral'}>
            {data.actions_applied}/{data.actions_parsed}
          </DebugChip>
          {creates > 0 && <DebugChip tone="success">+{creates}</DebugChip>}
          {updates > 0 && <DebugChip tone="warning">~{updates}</DebugChip>}
          {deletes > 0 && <DebugChip tone="destructive">-{deletes}</DebugChip>}
        </>
      }
    >
      <div className="grid grid-cols-2 gap-x-4 gap-y-0.5">
        <MetricRow label="Actions parsed" value={data.actions_parsed} />
        <MetricRow label="Actions applied" value={data.actions_applied} highlight={hasActions} />
      </div>

      {entries.length > 0 ? (
        <div className="space-y-1.5">
          {entries.map((entry, index) => {
            const themeEmoji = entry.theme ? (THEME_EMOJI[entry.theme] ?? '') : '';
            const moodEmoji = entry.mood ? (MOOD_EMOJI[entry.mood] ?? '') : '';

            return (
              <div
                key={index}
                className="cursor-help rounded border border-border/50 bg-muted/30 p-2 text-xs"
                title={`${entry.full_title ?? entry.title ?? ''}\n\n${entry.content ?? ''}`}
              >
                <div className="flex items-center gap-1.5">
                  <ActionBadge action={entry.action} />
                  {themeEmoji && <span>{themeEmoji}</span>}
                  <span
                    className={cn(
                      'truncate font-medium',
                      entry.action === 'delete'
                        ? cn(TONE_TEXT.destructive, 'line-through opacity-70')
                        : 'text-primary'
                    )}
                  >
                    {entry.full_title ?? entry.title ?? entry.entry_id?.slice(0, 8) ?? '—'}
                  </span>
                  {moodEmoji && <span className="text-muted-foreground">{moodEmoji}</span>}
                </div>
                {entry.theme && (
                  <div className="mt-0.5 flex items-center gap-2 text-muted-foreground">
                    <span>{entry.theme.replace('_', ' ')}</span>
                    {entry.entry_id && (
                      <span className="font-mono text-[10px]">{entry.entry_id.slice(0, 8)}</span>
                    )}
                  </div>
                )}
              </div>
            );
          })}
        </div>
      ) : (
        <div className="rounded bg-muted/20 p-2 text-xs italic text-muted-foreground">
          No journal actions for this message.
        </div>
      )}
    </DebugSection>
  );
});
