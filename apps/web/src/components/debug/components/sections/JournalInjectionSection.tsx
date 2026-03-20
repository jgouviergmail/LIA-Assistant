/**
 * Journal Injection Section Component
 *
 * Displays Personal Journals injection metrics in the debug panel.
 *
 * Shows:
 * - Entries found vs injected (budget constraint)
 * - Total characters injected vs budget
 * - Per-entry details: theme, title (25 chars), score, mood, source, date
 *
 * Phase: v1.7.0 - Personal Journals debug panel integration
 */

import React from 'react';
import { AccordionItem, AccordionTrigger, AccordionContent } from '@/components/ui/accordion';
import { cn } from '@/lib/utils';
import { MetricRow, SectionBadge } from '../shared';
import { CONFIDENCE_BAR_COLORS, SCORE_BAR_MAX_WIDTH_PX } from '../../utils/constants';
import type { JournalInjectionMetrics } from '@/types/chat';

export interface JournalInjectionSectionProps {
  /** Journal injection metrics (can be undefined) */
  data: JournalInjectionMetrics | undefined;
}

/** Theme emoji mapping */
const THEME_EMOJI: Record<string, string> = {
  self_reflection: '\u{1F6AA}',
  user_observations: '\u{1F441}\uFE0F',
  ideas_analyses: '\u{1F4A1}',
  learnings: '\u{1F4DA}',
};

/** Source labels */
const SOURCE_LABEL: Record<string, string> = {
  conversation: '\u{1F4AC}',
  consolidation: '\u{1F504}',
  manual: '\u270F\uFE0F',
};

/**
 * Get color tier for a journal similarity score
 */
function getScoreColor(score: number): 'high' | 'medium' | 'low' {
  if (score >= 0.7) return 'high';
  if (score >= 0.5) return 'medium';
  return 'low';
}

/**
 * Section Journal Injection
 *
 * Displays Personal Journals injection details:
 * - Entries found and injected count
 * - Characters injected vs budget
 * - Per-entry score with visual bars, theme, title, metadata
 */
export const JournalInjectionSection = React.memo(function JournalInjectionSection({
  data,
}: JournalInjectionSectionProps) {
  if (!data) {
    return null;
  }

  const hasEntries = data.entries_injected > 0;

  return (
    <AccordionItem value="journal-injection">
      <AccordionTrigger className="py-2 text-sm">
        <div className="flex items-center gap-2">
          <span>Personal Journals</span>
          <SectionBadge
            passed={hasEntries}
            label={hasEntries ? `${data.entries_injected} entries` : 'NO MATCH'}
          />
          {hasEntries && (
            <span className="text-[10px] px-1.5 py-0.5 rounded font-medium bg-muted/50 text-muted-foreground border border-border/50">
              {data.total_chars_injected.toLocaleString()} / {data.max_chars_budget.toLocaleString()} chars
            </span>
          )}
        </div>
      </AccordionTrigger>
      <AccordionContent>
        <div className="space-y-3">
          {/* Summary metrics */}
          <div className="grid grid-cols-2 gap-x-4 gap-y-0.5">
            <MetricRow label="Entries found" value={data.entries_found} />
            <MetricRow label="Entries injected" value={data.entries_injected} highlight={hasEntries} />
            <MetricRow label="Chars injected" value={data.total_chars_injected.toLocaleString()} />
            <MetricRow label="Chars budget" value={data.max_chars_budget.toLocaleString()} />
            <MetricRow label="Max results" value={data.max_results_setting} />
          </div>

          {/* Per-entry details */}
          {data.entries.length > 0 && (
            <div className="border-t pt-2 space-y-2">
              <div className="text-xs text-muted-foreground font-medium">
                Scored entries ({data.entries.length})
              </div>
              <div className="space-y-1.5 max-h-56 overflow-y-auto">
                {data.entries.map((entry, index) => {
                  const tier = getScoreColor(entry.score);
                  const barWidth = Math.round(entry.score * SCORE_BAR_MAX_WIDTH_PX);
                  const themeEmoji = THEME_EMOJI[entry.theme] ?? '';
                  const sourceEmoji = SOURCE_LABEL[entry.source] ?? '';

                  return (
                    <div
                      key={index}
                      className={cn(
                        'text-xs p-2 rounded border',
                        entry.injected
                          ? 'bg-muted/30 border-border/50'
                          : 'bg-muted/10 border-border/30 opacity-50'
                      )}
                    >
                      <div className="flex items-center justify-between gap-2">
                        <div className="flex-1 min-w-0">
                          {/* Theme + Title */}
                          <div className="flex items-center gap-1.5">
                            <span className="shrink-0 text-[10px] font-mono text-muted-foreground">
                              #{index + 1}
                            </span>
                            <span>{themeEmoji}</span>
                            <span className="font-medium text-primary truncate">
                              {entry.title}
                            </span>
                            {!entry.injected && (
                              <span className="text-[9px] px-1 py-0 rounded bg-yellow-900/30 text-yellow-400 border border-yellow-700/50">
                                BUDGET
                              </span>
                            )}
                          </div>
                          {/* Metadata row */}
                          <div className="flex items-center gap-2 mt-0.5 text-muted-foreground">
                            <span>{entry.date}</span>
                            <span>{sourceEmoji} {entry.source}</span>
                            <span>{entry.char_count} chars</span>
                          </div>
                        </div>
                        {/* Score with visual bar */}
                        <div className="flex items-center gap-2 shrink-0">
                          <div
                            className="h-1.5 rounded-full bg-muted/50"
                            style={{ width: `${SCORE_BAR_MAX_WIDTH_PX}px` }}
                          >
                            <div
                              className={cn(
                                'h-full rounded-full transition-all',
                                CONFIDENCE_BAR_COLORS[tier]
                              )}
                              style={{ width: `${barWidth}px` }}
                            />
                          </div>
                          <span
                            className={cn(
                              'text-[10px] font-mono w-10 text-right',
                              tier === 'high'
                                ? 'text-green-400'
                                : tier === 'medium'
                                  ? 'text-yellow-400'
                                  : 'text-red-400'
                            )}
                          >
                            {entry.score.toFixed(3)}
                          </span>
                        </div>
                      </div>
                    </div>
                  );
                })}
              </div>

              {/* Score legend */}
              <div className="flex items-center gap-3 text-[9px] text-muted-foreground pt-1">
                <span className="flex items-center gap-1">
                  <span className="w-2 h-2 rounded-full bg-green-500" />
                  {'≥0.70'}
                </span>
                <span className="flex items-center gap-1">
                  <span className="w-2 h-2 rounded-full bg-yellow-500" />
                  0.50-0.69
                </span>
                <span className="flex items-center gap-1">
                  <span className="w-2 h-2 rounded-full bg-red-400" />
                  {'<0.50'}
                </span>
              </div>
            </div>
          )}

          {/* No results message */}
          {!hasEntries && data.entries_found === 0 && (
            <div className="mt-1 text-xs text-muted-foreground bg-muted/20 p-2 rounded border border-border/50">
              No journal entries found. The assistant hasn&apos;t written any entries yet, or journals are disabled.
            </div>
          )}
        </div>
      </AccordionContent>
    </AccordionItem>
  );
});
