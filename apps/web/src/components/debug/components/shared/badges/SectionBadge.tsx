/**
 * Section Badge Component
 *
 * Pass/fail badge with optional score for section headers, rendered
 * through the design-system `Badge` (success/destructive tokens) so it
 * follows the five themes and the contrast guard.
 */

import React from 'react';
import { cn } from '@/lib/utils';
import { DebugChip } from '../DebugChip';
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
  /** Additional CSS classes */
  className?: string;
}

/**
 * Section status badge with optional score.
 *
 * @example
 * ```tsx
 * <SectionBadge passed={true} value={0.85} />   // "PASS 85%"
 * <SectionBadge passed={false} value={0.12} />  // "FAIL 12%"
 * <SectionBadge passed={true} label="OK" />     // "OK"
 * ```
 */
export const SectionBadge = React.memo(function SectionBadge({
  passed,
  value,
  label,
  showValue = value !== undefined,
  className,
}: SectionBadgeProps) {
  const displayLabel = label || (passed ? 'PASS' : 'FAIL');
  const ariaLabel = `Status: ${displayLabel}${value !== undefined ? ` ${formatPercent(value)}` : ''}`;

  return (
    <DebugChip
      tone={passed ? 'success' : 'destructive'}
      aria-label={ariaLabel}
      className={cn('ml-2', className)}
    >
      {displayLabel}
      {showValue && value !== undefined && (
        <span className="ml-1 font-mono">{formatPercent(value)}</span>
      )}
    </DebugChip>
  );
});
