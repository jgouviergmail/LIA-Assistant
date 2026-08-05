/**
 * Zone Badge Component
 *
 * Colored badge for token-budget zones. `emergency` is the only SOLID
 * fill (ADR-205 doctrine: density, not hue alone, carries the top level).
 */

import React from 'react';
import { DebugChip } from '../DebugChip';
import { zoneTone } from '../../../utils/tones';

export interface ZoneBadgeProps {
  /** Budget zone */
  zone: 'safe' | 'warning' | 'critical' | 'emergency';
  /** Additional CSS classes */
  className?: string;
}

/** Budget zone badge with severity tone. */
export const ZoneBadge = React.memo(function ZoneBadge({ zone, className }: ZoneBadgeProps) {
  return (
    <DebugChip tone={zoneTone(zone)} aria-label={`Zone: ${zone}`} className={className}>
      {zone}
    </DebugChip>
  );
});
