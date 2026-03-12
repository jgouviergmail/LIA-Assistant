/**
 * Confidence Badge Component
 *
 * Displays a colored badge for the confidence level (high/medium/low).
 * Reuses centralized color constants.
 */

import React from 'react';
import { cn } from '@/lib/utils';
import { CONFIDENCE_COLORS, BADGE_SIZES } from '../../../utils/constants';

export interface ConfidenceBadgeProps {
  /** Confidence level */
  confidence: 'high' | 'medium' | 'low';
  /** Badge size (default: 'sm') */
  size?: keyof typeof BADGE_SIZES;
  /** Additional CSS classes */
  className?: string;
}

/**
 * Confidence badge with semantic color
 *
 * Colors:
 * - high: green (success, high confidence)
 * - medium: yellow (warning, medium confidence)
 * - low: red (error, low confidence)
 *
 * @example
 * ```tsx
 * <ConfidenceBadge confidence="high" />
 * <ConfidenceBadge confidence="medium" size="md" />
 * <ConfidenceBadge confidence="low" className="ml-2" />
 * ```
 */
export const ConfidenceBadge = React.memo(function ConfidenceBadge({
  confidence,
  size = 'sm',
  className,
}: ConfidenceBadgeProps) {
  const colorClass = CONFIDENCE_COLORS[confidence];
  const sizeClass = BADGE_SIZES[size];

  return (
    <span
      className={cn(
        'inline-flex items-center rounded-full border font-medium uppercase tracking-wide',
        colorClass,
        sizeClass,
        className
      )}
      aria-label={`Confidence: ${confidence}`}
    >
      {confidence}
    </span>
  );
});
