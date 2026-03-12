/**
 * Zone Badge Component
 *
 * Displays a colored badge for token budget zones (safe/warning/critical/emergency).
 */

import React from 'react';
import { cn } from '@/lib/utils';
import { ZONE_COLORS, BADGE_SIZES } from '../../../utils/constants';

export interface ZoneBadgeProps {
  /** Budget zone */
  zone: 'safe' | 'warning' | 'critical' | 'emergency';
  /** Badge size (default: 'sm') */
  size?: keyof typeof BADGE_SIZES;
  /** Additional CSS classes */
  className?: string;
}

/**
 * Budget zone badge with semantic color
 *
 * Colors:
 * - safe: green (below safe limit)
 * - warning: yellow (approaching the limit)
 * - critical: orange (critical limit reached)
 * - emergency: red (maximum limit exceeded/near)
 *
 * @example
 * ```tsx
 * <ZoneBadge zone="safe" />
 * <ZoneBadge zone="warning" size="md" />
 * <ZoneBadge zone="emergency" className="ml-2" />
 * ```
 */
export const ZoneBadge = React.memo(function ZoneBadge({
  zone,
  size = 'sm',
  className,
}: ZoneBadgeProps) {
  const colorClass = ZONE_COLORS[zone];
  const sizeClass = BADGE_SIZES[size];

  return (
    <span
      className={cn(
        'inline-flex items-center rounded-full font-medium uppercase tracking-wide',
        colorClass,
        sizeClass,
        className
      )}
      aria-label={`Zone: ${zone}`}
    >
      {zone}
    </span>
  );
});
