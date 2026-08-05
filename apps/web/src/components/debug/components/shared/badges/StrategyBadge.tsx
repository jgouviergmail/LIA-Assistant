/**
 * Strategy Badge Component
 *
 * Colored badge for the planner strategy, graded by how degraded the
 * planning path is (template bypass = best economy, panic = emergency).
 */

import React from 'react';
import { DebugChip } from '../DebugChip';
import { strategyTone } from '../../../utils/tones';

export interface StrategyBadgeProps {
  /** Planning strategy */
  strategy: 'template_bypass' | 'filtered_catalogue' | 'generative' | 'panic_mode';
  /** Additional CSS classes */
  className?: string;
}

/** Short display labels for strategies (full name in tooltip). */
const STRATEGY_LABELS: Record<StrategyBadgeProps['strategy'], string> = {
  template_bypass: 'Template',
  filtered_catalogue: 'Filtered',
  generative: 'Generative',
  panic_mode: 'Panic',
};

/** Planning strategy badge with degradation tone. */
export const StrategyBadge = React.memo(function StrategyBadge({
  strategy,
  className,
}: StrategyBadgeProps) {
  return (
    <DebugChip
      tone={strategyTone(strategy)}
      aria-label={`Strategy: ${strategy}`}
      title={strategy}
      className={className}
    >
      {STRATEGY_LABELS[strategy]}
    </DebugChip>
  );
});
