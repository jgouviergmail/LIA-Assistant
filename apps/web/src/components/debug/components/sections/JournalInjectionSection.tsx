/**
 * Journal Section Component
 *
 * Displays Personal Journals injection metrics in two sub-sections:
 *
 * 1. **Injection (Planner)** — context retrieval for the planner node
 *    (happens BEFORE planning; annotated with its phase).
 * 2. **Injection (Response)** — context retrieval for the response node.
 *
 * Extraction lives in its own sibling section (JournalExtractionSection).
 */

import React from 'react';
import { NotebookPen } from 'lucide-react';
import {
  DebugChip,
  DebugSection,
  EmptySection,
  MetricRow,
  ScoreBar,
  ScoreLegend,
  SectionBadge,
  SubSectionHeader,
} from '../shared';
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
  user_observations: '\u{1F441}️',
  ideas_analyses: '\u{1F4A1}',
  learnings: '\u{1F4DA}',
};

/** Source labels */
const SOURCE_LABEL: Record<string, string> = {
  conversation: '\u{1F4AC}',
  consolidation: '\u{1F504}',
  manual: '✏️',
};

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
      <SubSectionHeader label={label} borderTop={showBorderTop} className="uppercase tracking-wider" />

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
        <div className="space-y-2 border-t border-border/50 pt-2">
          <SubSectionHeader label={`Entries (${data.entries.length})`} />
          <div className="space-y-1.5">
            {data.entries.map((entry, index) => {
              const isRecent = entry.score === null;
              const themeEmoji = THEME_EMOJI[entry.theme] ?? '';
              const sourceEmoji = SOURCE_LABEL[entry.source] ?? '';

              return (
                <div
                  key={index}
                  className={
                    entry.injected
                      ? 'rounded border border-border/50 bg-muted/30 p-2 text-xs'
                      : 'rounded border border-border/30 bg-muted/10 p-2 text-xs opacity-50'
                  }
                >
                  <div className="flex items-center justify-between gap-2">
                    <div
                      className="min-w-0 flex-1 cursor-help"
                      title={`${entry.full_title ?? entry.title}\n\n${entry.content ?? ''}`}
                    >
                      {/* Theme + Title */}
                      <div className="flex items-center gap-1.5">
                        <span className="shrink-0 font-mono text-[10px] text-muted-foreground">
                          #{index + 1}
                        </span>
                        <span>{themeEmoji}</span>
                        <span className="truncate font-medium text-primary">
                          {entry.full_title ?? entry.title}
                        </span>
                        {!entry.injected && <DebugChip tone="warning">BUDGET</DebugChip>}
                      </div>
                      {/* Metadata row */}
                      <div className="mt-0.5 flex items-center gap-2 text-muted-foreground">
                        <span>{entry.date}</span>
                        <span>
                          {sourceEmoji} {entry.source}
                        </span>
                        <span>{entry.char_count} chars</span>
                      </div>
                    </div>
                    {/* Score bar (or "recent" badge) */}
                    <div className="flex shrink-0 items-center gap-2">
                      {isRecent ? (
                        <DebugChip tone="info">RECENT</DebugChip>
                      ) : (
                        <ScoreBar score={entry.score!} space="relevance" />
                      )}
                    </div>
                  </div>
                </div>
              );
            })}
          </div>

          {/* Score legend */}
          <ScoreLegend space="relevance" />
        </div>
      )}
    </>
  );
}

/**
 * Section Personal Journals — Injection (Planner + Response)
 */
export const JournalInjectionSection = React.memo(function JournalInjectionSection({
  data,
  plannerData,
}: JournalInjectionSectionProps) {
  if (!data && !plannerData) {
    return (
      <EmptySection
        value="journal-injection"
        title="Personal Journals"
        icon={NotebookPen}
        message="No journal entries were retrieved (none exist yet, or journals are disabled)."
      />
    );
  }

  const hasResponseEntries = data ? data.entries_injected > 0 : false;
  const hasPlannerEntries = plannerData ? plannerData.entries_injected > 0 : false;
  const hasAnyInjection = hasResponseEntries || hasPlannerEntries;

  // Build badge label
  const parts: string[] = [];
  if (hasPlannerEntries) parts.push(`P:${plannerData!.entries_injected}`);
  if (hasResponseEntries) parts.push(`R:${data!.entries_injected}`);
  const badgeLabel = parts.length > 0 ? parts.join(' / ') : 'NO MATCH';

  return (
    <DebugSection
      value="journal-injection"
      title="Personal Journals"
      icon={NotebookPen}
      badge={<SectionBadge passed={hasAnyInjection} label={badgeLabel} />}
    >
      {/* Planner injection happens BEFORE planning — shown first (execution order). */}
      {plannerData && (
        <InjectionSubSection
          label="Context injection — Planner (before planning)"
          data={plannerData}
          showBorderTop={false}
        />
      )}

      {data && (
        <InjectionSubSection
          label="Context injection — Response"
          data={data}
          showBorderTop={Boolean(plannerData)}
        />
      )}

      {/* No injection results message */}
      {!hasAnyInjection && (
        <div className="mt-1 rounded border border-border/50 bg-muted/20 p-2 text-xs text-muted-foreground">
          No journal entries matched. The assistant hasn&apos;t written any entries yet, or
          journals are disabled.
        </div>
      )}
    </DebugSection>
  );
});
