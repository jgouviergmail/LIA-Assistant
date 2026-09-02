/**
 * BudgetBar — how much of an allowance this turn has spent.
 *
 * A ReAct turn has two allowances and they are one question asked twice:
 * iterations against their ceiling, and delegated tool time against its budget
 * (ADR-256). They were drawn by two copies of the same markup, which is how the
 * second one arrived without the first one's warning line. One component now,
 * so a bar cannot exist without the sentence that explains why it is full.
 *
 * The bound travels with the value it constrains (ADR-184): a caller that has
 * no `max` renders nothing rather than a bar scaled against an invented one.
 */

import React from 'react';
import { cn } from '@/lib/utils';
import { TONE_BAR, TONE_TEXT } from '../../utils/tones';

export interface BudgetBarProps {
  /** Amount consumed so far, in the caller's own unit. */
  value: number;
  /** The published bound. A non-positive bound renders nothing. */
  max: number;
  /** Names what the bar measures. Required in practice as soon as a caller
   *  draws TWO bars: stacked and unlabelled, they read as the same thing. */
  label?: string;
  /** Shown under the bar once the bound is reached. */
  exhaustedLabel: string;
  /** Additional CSS classes for the wrapper. */
  className?: string;
}

/** Horizontal allowance bar, warning-toned once the bound is reached. */
export const BudgetBar = React.memo(function BudgetBar({
  value,
  max,
  label,
  exhaustedLabel,
  className,
}: BudgetBarProps) {
  if (max <= 0) return null;

  const exhausted = value >= max;
  const ratio = Math.min(Math.max(value / max, 0), 1);

  return (
    <div className={className}>
      {/* Deliberately at the same 10px as `exhaustedLabel` below, not at the
          12px of `SubSectionHeader`: these two frame the bar and read as one
          unit, while a SubSectionHeader separates sub-blocks. The debug panel
          is an admin surface and is English throughout — no locale lookup
          here, and the primitive never invents a string of its own. */}
      {label && <div className="mb-0.5 text-[10px] text-muted-foreground">{label}</div>}
      <div className="h-1.5 w-full overflow-hidden rounded-full bg-muted/50">
        <div
          data-testid="budget-bar-fill"
          className={cn('h-full rounded-full', exhausted ? TONE_BAR.warning : TONE_BAR.info)}
          style={{ width: `${ratio * 100}%` }}
        />
      </div>
      {exhausted && (
        <div className={cn('mt-1 text-[10px]', TONE_TEXT.warning)}>{exhaustedLabel}</div>
      )}
    </div>
  );
});
