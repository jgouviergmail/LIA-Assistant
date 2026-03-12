/**
 * Threshold Row Component
 *
 * Displays a threshold comparison with pass/fail indicator.
 * Used to display thresholds in debug metrics.
 */

import React from 'react';
import { cn } from '@/lib/utils';
import { Check, X } from 'lucide-react';
import { formatValue } from '../../utils/formatters';
import { DEBUG_TEXT_SIZES } from '../../utils/constants';

export interface ThresholdCheck {
  /** Threshold value */
  value: number;
  /** Current measured value */
  actual: number;
  /** true if the threshold is passed */
  passed: boolean;
}

export interface ThresholdRowProps {
  /** Threshold label */
  label: string;
  /** Comparison data */
  check: ThresholdCheck;
  /** Additional CSS classes */
  className?: string;
}

/**
 * Threshold row with comparison and visual indicator
 *
 * Design:
 * - Displays: "Label: actual vs threshold ✓/✗"
 * - Green if passed, red otherwise
 * - Check/cross icon for quick visual feedback
 *
 * @example
 * ```tsx
 * <ThresholdRow
 *   label="Primary Min"
 *   check={{
 *     value: 0.15,
 *     actual: 0.42,
 *     passed: true
 *   }}
 * />
 * // Displays: "Primary Min: 42% vs 15% ✓" (green)
 *
 * <ThresholdRow
 *   label="Hard Threshold"
 *   check={{
 *     value: 0.30,
 *     actual: 0.12,
 *     passed: false
 *   }}
 * />
 * // Displays: "Hard Threshold: 12% vs 30% ✗" (red)
 * ```
 */
export const ThresholdRow = React.memo(function ThresholdRow({
  label,
  check,
  className,
}: ThresholdRowProps) {
  const { value, actual, passed } = check;

  return (
    <div
      className={cn(
        'flex items-center justify-between gap-2 text-xs py-0.5',
        className
      )}
    >
      {/* Label */}
      <span className="text-muted-foreground flex-shrink-0">
        {label}:
      </span>

      {/* Comparison + Icon */}
      <div className="flex items-center gap-1.5">
        {/* Actual vs Threshold */}
        <span
          className={cn(
            `font-mono ${DEBUG_TEXT_SIZES.mono}`,
            passed ? 'text-green-700' : 'text-red-700'
          )}
        >
          {formatValue(actual)} vs {formatValue(value)}
        </span>

        {/* Icon */}
        {passed ? (
          <Check className="h-3 w-3 text-green-600 flex-shrink-0" strokeWidth={3} />
        ) : (
          <X className="h-3 w-3 text-red-600 flex-shrink-0" strokeWidth={3} />
        )}
      </div>
    </div>
  );
});
