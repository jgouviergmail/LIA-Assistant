/**
 * Section Badge Component
 *
 * Displays a pass/fail badge with score for section headers.
 * Used in AccordionTrigger to indicate if a section passed its thresholds.
 */

import React from 'react';
import { cn } from '@/lib/utils';
import { STATUS_COLORS, BADGE_SIZES } from '../../../utils/constants';
import { formatPercent } from '../../../utils/formatters';

export interface SectionBadgeProps {
  /** true if threshold passed, false otherwise */
  passed: boolean;
  /** Numeric value to display (typically a 0-1 score) */
  value?: number;
  /** Custom label (otherwise "PASS"/"FAIL") */
  label?: string;
  /** Show value next to label (default: true if value provided) */
  showValue?: boolean;
  /** Badge size (default: 'sm') */
  size?: keyof typeof BADGE_SIZES;
  /** Additional CSS classes */
  className?: string;
}

/**
 * Section status badge with optional score
 *
 * Design:
 * - Green if passed=true, red if passed=false
 * - Shows score as percentage if provided
 * - Compact for header usage
 *
 * @example
 * ```tsx
 * <SectionBadge passed={true} value={0.85} />
 * // Displays: "PASS 85%"
 *
 * <SectionBadge passed={false} value={0.12} />
 * // Displays: "FAIL 12%"
 *
 * <SectionBadge passed={true} label="OK" />
 * // Displays: "OK"
 *
 * <SectionBadge passed={false} value={0.45} showValue={false} />
 * // Displays: "FAIL" (without score)
 * ```
 */
export const SectionBadge = React.memo(function SectionBadge({
  passed,
  value,
  label,
  showValue = value !== undefined,
  size = 'xs',
  className,
}: SectionBadgeProps) {
  const colorClass = passed ? STATUS_COLORS.passed : STATUS_COLORS.failed;
  const sizeClass = BADGE_SIZES[size];
  const displayLabel = label || (passed ? 'PASS' : 'FAIL');

  return (
    <span
      className={cn(
        'inline-flex items-center rounded-full font-medium uppercase tracking-wide ml-2',
        colorClass,
        sizeClass,
        className
      )}
      aria-label={`Status: ${displayLabel}${value !== undefined ? ` ${formatPercent(value)}` : ''}`}
    >
      {displayLabel}
      {showValue && value !== undefined && (
        <span className="ml-1 font-mono">{formatPercent(value)}</span>
      )}
    </span>
  );
});
