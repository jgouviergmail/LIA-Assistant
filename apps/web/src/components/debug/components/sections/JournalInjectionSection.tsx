/**
 * Journal Section Component
 *
 * Displays Personal Journals debug metrics in three sub-sections:
 *
 * 1. **Injection (Response)** (context retrieval for response node):
 *    - Entries found vs injected (budget constraint)
 *    - Total characters injected vs budget
 *    - Per-entry details: theme, title (25 chars), score, mood, source, date
 *
 * 2. **Injection (Planner)** (context retrieval for planner node):
 *    - Same structure as Response injection
 *
 * 3. **Extraction** (background creation):
 *    - Actions parsed from LLM output vs applied
 *    - Per-action details: action type, theme, title, mood
 *
 * Phase: v1.7.0/v1.7.1 - Personal Journals debug panel integration
 * Phase: v1.8.0 - Journal extraction debug panel
 * Phase: v1.9.2 - Planner injection debug panel
 */

import React from 'react';
import { AccordionItem, AccordionTrigger, AccordionContent } from '@/components/ui/accordion';
import { cn } from '@/lib/utils';
import { EmptySection, MetricRow, SectionBadge } from '../shared';
import { CONFIDENCE_BAR_COLORS, SCORE_BAR_MAX_WIDTH_PX } from '../../utils/constants';
import type { JournalInjectionMetrics } from '@/types/chat';

export interface JournalInjectionSectionProps {
  /** Journal injection metrics from response node (can be undefined) */
  data: JournalInjectionMetrics | undefined;
  /** Journal injection metrics from planner node (can be undefined) */
  plannerData: JournalInjectionMetrics | undefined;
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
 * Injection sub-section — reused for both Response and Planner injection
 */
function InjectionSubSection({
  label,
  data,
  showBorderTop,
}: {
  label: string;
  data: JournalInjectionMetrics;
  showBorderTop: boolean;
}) {
  const hasInjected = data.entries_injected > 0;

  return (
    <>
      <div
        className={cn(
          'text-xs font-medium text-muted-foreground uppercase tracking-wider',
          showBorderTop && 'border-t pt-3'
        )}
      >
        {label}
      </div>

      {/* Summary metrics */}
      <div className="grid grid-cols-2 gap-x-4 gap-y-0.5">
        <MetricRow label="Entries found" value={data.entries_found} />
        {(data.entries_recent ?? 0) > 0 && (
          <MetricRow label="Recent injected" value={data.entries_recent!} />
        )}
        <MetricRow label="Entries injected" value={data.entries_injected} highlight={hasInjected} />
        <MetricRow label="Chars injected" value={data.total_chars_injected.toLocaleString()} />
        <MetricRow label="Chars budget" value={data.max_chars_budget.toLocaleString()} />
        <MetricRow label="Max results" value={data.max_results_setting} />
      </div>

      {/* Per-entry details */}
      {data.entries.length > 0 && (
        <div className="border-t pt-2 space-y-2">
          <div className="text-xs text-muted-foreground font-medium">
            Entries ({data.entries.length})
          </div>
          <div className="space-y-1.5 space-y-1.5">
            {data.entries.map((entry, index) => {
              const isRecent = entry.score === null;
              const tier = isRecent ? ('medium' as const) : getScoreColor(entry.score!);
              const barWidth = isRecent ? 0 : Math.round(entry.score! * SCORE_BAR_MAX_WIDTH_PX);
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
                    <div
                      className="flex-1 min-w-0 cursor-help"
                      title={`${entry.full_title ?? entry.title}\n\n${entry.content ?? ''}`}
                    >
                      {/* Theme + Title */}
                      <div className="flex items-center gap-1.5">
                        <span className="shrink-0 text-[10px] font-mono text-muted-foreground">
                          #{index + 1}
                        </span>
                        <span>{themeEmoji}</span>
                        <span className="font-medium text-primary truncate">
                          {entry.full_title ?? entry.title}
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
                        <span>
                          {sourceEmoji} {entry.source}
                        </span>
                        <span>{entry.char_count} chars</span>
                      </div>
                    </div>
                    {/* Score with visual bar (or "recent" badge) */}
                    <div className="flex items-center gap-2 shrink-0">
                      {isRecent ? (
                        <span className="text-[9px] px-1.5 py-0 rounded font-mono border bg-blue-900/30 text-blue-400 border-blue-700/50">
                          RECENT
                        </span>
                      ) : (
                        <>
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
                            {entry.score!.toFixed(3)}
                          </span>
                        </>
                      )}
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
    </>
  );
}

/**
 * Section Journal — Injection (Response + Planner) + Extraction
 *
 * Displays Personal Journals debug details:
 * - Injection (Response): entries found/injected for response node
 * - Injection (Planner): entries found/injected for planner node
 * - Extraction: actions parsed/applied, per-action details
 */
export const JournalInjectionSection = React.memo(function JournalInjectionSection({
  data,
  plannerData,
}: JournalInjectionSectionProps) {
  if (!data && !plannerData) {
    return <EmptySection value="journal-injection" title="Personal Journals" />;
  }

  const hasResponseEntries = data ? data.entries_injected > 0 : false;
  const hasPlannerEntries = plannerData ? plannerData.entries_injected > 0 : false;
  const hasAnyInjection = hasResponseEntries || hasPlannerEntries;

  // Build badge label
  const parts: string[] = [];
  if (hasResponseEntries) parts.push(`R:${data!.entries_injected}`);
  if (hasPlannerEntries) parts.push(`P:${plannerData!.entries_injected}`);
  const badgeLabel = parts.length > 0 ? parts.join(' / ') : 'NO MATCH';

  return (
    <AccordionItem value="journal-injection">
      <AccordionTrigger className="py-2 text-sm">
        <div className="flex items-center gap-2">
          <span>Personal Journals</span>
          <SectionBadge passed={hasAnyInjection} label={badgeLabel} />
        </div>
      </AccordionTrigger>
      <AccordionContent>
        <div className="space-y-3">
          {/* ============================================================ */}
          {/* INJECTION SUB-SECTION — Response Node */}
          {/* ============================================================ */}
          {data && (
            <InjectionSubSection
              label="Context Injection (Response)"
              data={data}
              showBorderTop={false}
            />
          )}

          {/* ============================================================ */}
          {/* INJECTION SUB-SECTION — Planner Node */}
          {/* ============================================================ */}
          {plannerData && (
            <InjectionSubSection
              label="Context Injection (Planner)"
              data={plannerData}
              showBorderTop={!!data}
            />
          )}

          {/* No injection results message */}
          {!hasAnyInjection && (
            <div className="mt-1 text-xs text-muted-foreground bg-muted/20 p-2 rounded border border-border/50">
              No journal entries found. The assistant hasn&apos;t written any entries yet, or
              journals are disabled.
            </div>
          )}
        </div>
      </AccordionContent>
    </AccordionItem>
  );
});
