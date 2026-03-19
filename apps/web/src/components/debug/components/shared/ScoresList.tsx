/**
 * Scores List Component
 *
 * Displays a list of scores with progress bars.
 * Used for domain_selection and tool_selection scores.
 *
 * v3.1 LLM-based: Simplified display (no more CAL/RAW).
 */

import React from 'react';
import { cn } from '@/lib/utils';
import { formatPercent } from '../../utils/formatters';
import {
  SCORE_BAR_MAX_WIDTH_PX,
  MAX_SCORES_DISPLAY,
  DEFAULT_DOMAIN_THRESHOLD,
  DEBUG_TEXT_SIZES,
  DEBUG_WIDTHS,
} from '../../utils/constants';

export interface ScoresListProps {
  /** Confidence scores (domain/tool name -> score) */
  scores: Record<string, number>;
  /** Section label (default: "Scores") */
  label?: string;
  /** Threshold for green coloring (default: DEFAULT_DOMAIN_THRESHOLD) */
  passThreshold?: number;
  /**
   * Explicitly selected items (colored in green).
   * If provided, replaces the passThreshold-based logic.
   * Useful for v3.1 LLM-based where selected domains are known.
   */
  selectedItems?: string[];
  /** Maximum number of scores to display (default: MAX_SCORES_DISPLAY) */
  maxDisplay?: number;
  /** Additional CSS classes */
  className?: string;
}

/**
 * Score list with progress bars
 *
 * Design:
 * - Sorted by descending score
 * - Progress bar proportional to max score
 * - Green if score >= threshold, red otherwise
 * - Limited to maxDisplay entries to save space
 *
 * @example
 * ```tsx
 * <ScoresList
 *   scores={{
 *     calendar: 0.95,
 *     contacts: 0.95,
 *     drive: 0.12,
 *   }}
 *   label="Confiance par domaine"
 *   passThreshold={0.15}
 * />
 * ```
 */
export const ScoresList = React.memo(function ScoresList({
  scores,
  label = 'Scores',
  passThreshold = DEFAULT_DOMAIN_THRESHOLD,
  selectedItems,
  maxDisplay = MAX_SCORES_DISPLAY,
  className,
}: ScoresListProps) {
  // Set for O(1) lookup of selected items
  const selectedSet = React.useMemo(() => {
    return selectedItems ? new Set(selectedItems) : null;
  }, [selectedItems]);

  // Sort by descending score, but put selected items first
  const sortedEntries = React.useMemo(() => {
    const entries = Object.entries(scores);

    if (selectedSet) {
      // If selectedItems provided, sort: selected first (by desc score), then others (by desc score)
      return entries
        .sort(([nameA, scoreA], [nameB, scoreB]) => {
          const aSelected = selectedSet.has(nameA);
          const bSelected = selectedSet.has(nameB);
          if (aSelected && !bSelected) return -1;
          if (!aSelected && bSelected) return 1;
          return scoreB - scoreA;
        })
        .slice(0, maxDisplay);
    }

    // Otherwise, simple sort by descending score
    return entries.sort(([, a], [, b]) => b - a).slice(0, maxDisplay);
  }, [scores, selectedSet, maxDisplay]);

  // Max score for normalizing bars
  const maxScore = React.useMemo(() => {
    return Math.max(...Object.values(scores), 0.01); // min 0.01 to avoid division by zero
  }, [scores]);

  if (sortedEntries.length === 0) {
    return (
      <div className={cn('text-xs text-muted-foreground italic', className)}>
        Aucun score disponible
      </div>
    );
  }

  return (
    <div className={cn('space-y-1', className)}>
      {/* Label */}
      <div className="text-xs text-muted-foreground font-medium mb-1.5">{label}</div>

      {/* Scores list */}
      {sortedEntries.map(([name, score]) => {
        // If selectedItems provided, use that to determine "passed"
        // Otherwise, use the classic threshold logic
        const passed = selectedSet ? selectedSet.has(name) : score >= passThreshold;
        const barWidth = (score / maxScore) * SCORE_BAR_MAX_WIDTH_PX;

        return (
          <div key={name} className="flex items-center gap-2 text-xs">
            {/* Domain/tool name */}
            <span
              className={cn(
                'flex-shrink-0 w-20 truncate',
                passed ? 'text-foreground font-medium' : 'text-muted-foreground'
              )}
              title={name}
            >
              {name}
            </span>

            {/* Progress bar */}
            <div className="flex-1 flex items-center gap-2">
              <div
                className={`relative h-1.5 bg-muted rounded-full flex-1 ${DEBUG_WIDTHS.scoreBar}`}
              >
                <div
                  className={cn(
                    'absolute left-0 top-0 h-full rounded-full transition-all',
                    passed ? 'bg-green-500' : 'bg-red-400'
                  )}
                  style={{ width: `${barWidth}%` }}
                  aria-label={`Score: ${formatPercent(score)}`}
                />
              </div>

              {/* Numeric score */}
              <span
                className={cn(
                  `font-mono ${DEBUG_TEXT_SIZES.mono} ${DEBUG_WIDTHS.scoreValue} text-right`,
                  passed ? 'text-green-400 font-semibold' : 'text-red-400'
                )}
              >
                {formatPercent(score)}
              </span>
            </div>
          </div>
        );
      })}

      {/* Indicator if more scores available */}
      {Object.keys(scores).length > maxDisplay && (
        <div className={`${DEBUG_TEXT_SIZES.small} text-muted-foreground italic pt-0.5`}>
          + {Object.keys(scores).length - maxDisplay} autres
        </div>
      )}
    </div>
  );
});
