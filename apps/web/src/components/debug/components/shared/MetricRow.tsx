/**
 * Metric Row Component
 *
 * Displays a simple metric row with label and value.
 * Base component reused throughout the debug panel.
 */

import React from 'react';
import { cn } from '@/lib/utils';
import { formatValue } from '../../utils/formatters';
import { DEBUG_TEXT_SIZES, DEBUG_WIDTHS } from '../../utils/constants';

export interface MetricRowProps {
  /** Metric label */
  label: string;
  /** Metric value (automatically formatted) */
  value: string | number | boolean | null | undefined;
  /** Highlight (bold) */
  highlight?: boolean;
  /** Display in code mode (mono font) */
  mono?: boolean;
  /** Truncate long values */
  truncate?: boolean;
  /** Additional CSS classes for the value */
  valueClassName?: string;
  /** Additional CSS classes for the row */
  className?: string;
}

/**
 * Generic metric row
 *
 * Design:
 * - Flex layout with label on the left, value on the right
 * - Automatic formatting via formatValue()
 * - Supports highlight and mono
 * - Compact (text-xs) to save space
 *
 * @example
 * ```tsx
 * <MetricRow label="Confidence" value={0.85} />
 * // Displays: Confidence         85%
 *
 * <MetricRow label="Route" value="planner" highlight />
 * // Displays: Route         planner (bold)
 *
 * <MetricRow label="Query ID" value="abc123" mono />
 * // Displays: Query ID         abc123 (monospace)
 * ```
 */
export const MetricRow = React.memo(function MetricRow({
  label,
  value,
  highlight = false,
  mono = false,
  truncate = false,
  valueClassName,
  className,
}: MetricRowProps) {
  const formattedValue = formatValue(value);

  return (
    <div
      className={cn(
        'flex items-baseline justify-between gap-2 text-xs py-0.5',
        className
      )}
    >
      {/* Label */}
      <span className="text-muted-foreground flex-shrink-0">
        {label}:
      </span>

      {/* Value */}
      <span
        className={cn(
          'text-right',
          highlight && 'font-semibold text-foreground',
          mono && `font-mono ${DEBUG_TEXT_SIZES.mono}`,
          truncate && `truncate ${DEBUG_WIDTHS.truncatedValue}`,
          valueClassName
        )}
        title={truncate && formattedValue.length > 30 ? formattedValue : undefined}
      >
        {formattedValue}
      </span>
    </div>
  );
});
