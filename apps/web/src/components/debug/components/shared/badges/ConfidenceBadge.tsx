/**
 * Confidence Badge Component
 *
 * Colored badge for a high/medium/low confidence level, toned through the
 * shared semantic mapper (success/warning/destructive tokens).
 */

import React from 'react';
import { DebugChip } from '../DebugChip';
import { confidenceTone } from '../../../utils/tones';

export interface ConfidenceBadgeProps {
  /** Confidence level */
  confidence: 'high' | 'medium' | 'low';
  /** Additional CSS classes */
  className?: string;
}

/** Confidence badge with semantic tone. */
export const ConfidenceBadge = React.memo(function ConfidenceBadge({
  confidence,
  className,
}: ConfidenceBadgeProps) {
  return (
    <DebugChip
      tone={confidenceTone(confidence)}
      aria-label={`Confidence: ${confidence}`}
      className={className}
    >
      {confidence}
    </DebugChip>
  );
});
