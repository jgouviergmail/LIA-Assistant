/**
 * EmptySection — collapsed placeholder for a section without data.
 *
 * NEUTRAL by doctrine: an optional stage that did not run is not a
 * failure, so the badge is the inert secondary tone (the old red "FAIL
 * N/A" was a false-negative signal). An optional message explains WHY the
 * section is empty when the reason is known.
 */

import React from 'react';
import type { LucideIcon } from 'lucide-react';
import { DebugSection } from './DebugSection';
import { DebugChip } from './DebugChip';

export interface EmptySectionProps {
  /** Unique accordion value */
  value: string;
  /** Section title */
  title: string;
  /** Themed title icon (same icon as the populated section). */
  icon?: LucideIcon;
  /** Contextual reason shown in the content area. */
  message?: string;
}

/** Placeholder for sections with no data. */
export const EmptySection = React.memo(function EmptySection({
  value,
  title,
  icon,
  message = 'No data for this section on this request.',
}: EmptySectionProps) {
  return (
    <DebugSection value={value} title={title} icon={icon} badge={<DebugChip tone="neutral">N/A</DebugChip>}>
      <div className="rounded border border-border/50 bg-muted/20 p-2 text-xs text-muted-foreground">
        {message}
      </div>
    </DebugSection>
  );
});
