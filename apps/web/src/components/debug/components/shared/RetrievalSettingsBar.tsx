/**
 * RetrievalSettingsBar — the bounds a retrieval section enforced, shown inline.
 *
 * Memory injection and RAG injection both publish the threshold and the cap
 * that produced their results. Rendering them through `MetricRow` is wrong:
 * `formatValue` turns 0.62 into "62%", and a cosine threshold is not a
 * percentage. Both sections used to hand-roll the same flex row instead; this
 * is that row, once.
 *
 * The values are shown raw and monospaced so they can be compared with the
 * per-item scores above them, and with the tick `ScoreBar` draws at `min_score`.
 */

import React from 'react';
import { cn } from '@/lib/utils';

export interface RetrievalSettingsBarProps {
  /** Minimum score an item needed to be injected (raw, not a percentage). */
  minScore: number;
  /** Maximum number of items the turn could inject. */
  maxResults: number;
  /** Additional CSS classes. */
  className?: string;
}

/** Inline summary of the retrieval bounds in force for a section. */
export const RetrievalSettingsBar = React.memo(function RetrievalSettingsBar({
  minScore,
  maxResults,
  className,
}: RetrievalSettingsBarProps) {
  return (
    <div
      className={cn(
        'flex flex-wrap items-center gap-x-3 gap-y-1 rounded bg-muted/20 p-2 text-[10px] text-muted-foreground',
        className
      )}
    >
      <span>
        <strong>min_score:</strong> <span className="font-mono">{minScore}</span>
      </span>
      <span>
        <strong>max_results:</strong> <span className="font-mono">{maxResults}</span>
      </span>
    </div>
  );
});
