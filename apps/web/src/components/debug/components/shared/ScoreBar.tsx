/**
 * ScoreBar — the single score visualization of the debug panel.
 *
 * Replaces four divergent inline implementations. The fill takes the tier
 * tone from the shared score-space table, and — new — the decision
 * threshold is drawn ON the bar, so "why did this pass/fail" is read in
 * place instead of reconciling a bar with a number elsewhere.
 */

import React from 'react';
import { cn } from '@/lib/utils';
import { TONE_BAR, type ScoreSpace, scoreTier, tierTone } from '../../utils/tones';

export interface ScoreBarProps {
  /** Score in 0..1 (clamped for display). */
  score: number;
  /** Score space deciding the tier thresholds. */
  space: ScoreSpace;
  /** Optional decision threshold (0..1) drawn as a tick on the bar. */
  threshold?: number;
  /** Show the numeric value next to the bar (default true). */
  showValue?: boolean;
  /** Additional CSS classes for the wrapper. */
  className?: string;
}

/** Horizontal score bar with tier tone and optional threshold tick. */
export const ScoreBar = React.memo(function ScoreBar({
  score,
  space,
  threshold,
  showValue = true,
  className,
}: ScoreBarProps) {
  const clamped = Math.min(Math.max(score, 0), 1);
  const tone = tierTone(scoreTier(clamped, space));

  return (
    <div className={cn('flex items-center gap-1.5', className)}>
      <div className="relative h-1.5 w-[100px] shrink-0 rounded-full bg-muted/50">
        <div
          data-testid="score-bar-fill"
          className={cn('h-full rounded-full transition-all', TONE_BAR[tone])}
          style={{ width: `${clamped * 100}%` }}
        />
        {threshold !== undefined && (
          <div
            data-testid="score-bar-threshold"
            className="absolute top-1/2 h-2.5 w-px -translate-y-1/2 bg-foreground/60"
            style={{ left: `${Math.min(Math.max(threshold, 0), 1) * 100}%` }}
            title={`Threshold: ${threshold}`}
          />
        )}
      </div>
      {showValue && (
        <span className="w-10 text-right font-mono text-[11px] text-muted-foreground">
          {clamped.toFixed(3)}
        </span>
      )}
    </div>
  );
});
