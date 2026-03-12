/**
 * Info Row Component
 *
 * Displays threshold information without comparison.
 * Used for informational thresholds (no pass/fail).
 */

import React from 'react';
import { cn } from '@/lib/utils';
import { Info } from 'lucide-react';
import { formatValue } from '../../utils/formatters';
import { DEBUG_TEXT_SIZES } from '../../utils/constants';

export interface ThresholdInfo {
  /** Threshold value (can be string or number) */
  value: string | number;
  /** Optional additional information */
  info?: string;
}

export interface InfoRowProps {
  /** Information label */
  label: string;
  /** Informational threshold data */
  check: ThresholdInfo;
  /** Show info icon (default: false) */
  showIcon?: boolean;
  /** Additional CSS classes */
  className?: string;
}

/**
 * Threshold information row (without comparison)
 *
 * Design:
 * - Displays: "Label: value"
 * - Optional info icon if additional information provided
 * - Neutral color (no green/red)
 *
 * Difference with ThresholdRow:
 * - ThresholdRow: for comparisons (actual vs threshold, pass/fail)
 * - InfoRow: for informational values (temperature, max_domains, etc.)
 *
 * @example
 * ```tsx
 * <InfoRow
 *   label="Softmax Temperature"
 *   check={{ value: 0.1, info: "Sharp discrimination" }}
 *   showIcon
 * />
 * // Displays: "Softmax Temperature: 10% ℹ"
 *
 * <InfoRow
 *   label="Max Domains"
 *   check={{ value: 3 }}
 * />
 * // Displays: "Max Domains: 3"
 * ```
 */
export const InfoRow = React.memo(function InfoRow({
  label,
  check,
  showIcon = false,
  className,
}: InfoRowProps) {
  const { value, info } = check;

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

      {/* Value + Icon */}
      <div className="flex items-center gap-1.5">
        {/* Value */}
        <span className={`font-mono ${DEBUG_TEXT_SIZES.mono} text-foreground`}>
          {formatValue(value)}
        </span>

        {/* Info icon with tooltip */}
        {showIcon && info && (
          <Info
            className="h-3 w-3 text-blue-500 flex-shrink-0"
            aria-label={info}
          />
        )}
      </div>
    </div>
  );
});
