/**
 * Strategy Badge Component
 *
 * Displays a colored badge for the planner strategy
 * (template_bypass/filtered_catalogue/generative/panic_mode).
 */

import React from 'react';
import { cn } from '@/lib/utils';
import { STRATEGY_COLORS, BADGE_SIZES } from '../../../utils/constants';

export interface StrategyBadgeProps {
  /** Planning strategy */
  strategy: 'template_bypass' | 'filtered_catalogue' | 'generative' | 'panic_mode';
  /** Badge size (default: 'sm') */
  size?: keyof typeof BADGE_SIZES;
  /** Additional CSS classes */
  className?: string;
}

/**
 * Planning strategy badge with semantic color
 *
 * Colors:
 * - template_bypass: blue (maximum optimization, direct template)
 * - filtered_catalogue: green (intelligent filter, perf/quality balance)
 * - generative: purple (full generation, max quality)
 * - panic_mode: red (emergency fallback, token limit reached)
 *
 * @example
 * ```tsx
 * <StrategyBadge strategy="template_bypass" />
 * <StrategyBadge strategy="generative" size="md" />
 * <StrategyBadge strategy="panic_mode" className="ml-2" />
 * ```
 */
export const StrategyBadge = React.memo(function StrategyBadge({
  strategy,
  size = 'sm',
  className,
}: StrategyBadgeProps) {
  const colorClass = STRATEGY_COLORS[strategy];
  const sizeClass = BADGE_SIZES[size];

  // More readable labels
  const strategyLabels: Record<typeof strategy, string> = {
    template_bypass: 'Template',
    filtered_catalogue: 'Filtered',
    generative: 'Generative',
    panic_mode: 'Panic',
  };

  return (
    <span
      className={cn(
        'inline-flex items-center rounded-full font-medium uppercase tracking-wide',
        colorClass,
        sizeClass,
        className
      )}
      aria-label={`Strategy: ${strategy}`}
      title={strategy} // Full strategy name in tooltip
    >
      {strategyLabels[strategy]}
    </span>
  );
});
