/**
 * SubSectionHeader — the uniform labelled separator inside a section.
 *
 * One shape for every sub-block heading (the panel previously mixed five
 * ad-hoc variants of the same muted label).
 */

import React from 'react';
import { cn } from '@/lib/utils';

export interface SubSectionHeaderProps {
  /** Sub-block label. */
  label: string;
  /** Draw a top border separator above the header (default false). */
  borderTop?: boolean;
  /** Additional CSS classes. */
  className?: string;
}

/** Uniform sub-section heading. */
export const SubSectionHeader = React.memo(function SubSectionHeader({
  label,
  borderTop = false,
  className,
}: SubSectionHeaderProps) {
  return (
    <div
      className={cn(
        'mb-1.5 text-xs font-medium text-muted-foreground',
        borderTop && 'border-t border-border/50 pt-2',
        className
      )}
    >
      {label}
    </div>
  );
});
