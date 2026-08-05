/**
 * DebugChip — semantic status chip for the debug panel.
 *
 * Thin wrapper over the design-system `Badge`: the tone resolves to a Badge
 * variant, so every chip inherits the theme-aware tokens and the app-wide
 * contrast guard instead of hand-painted palette classes.
 */

import React from 'react';
import { Badge } from '@/components/ui/badge';
import { cn } from '@/lib/utils';
import { type DebugTone, badgeVariantFor } from '../../utils/tones';

export interface DebugChipProps {
  /** Semantic tone (resolved to a Badge variant). */
  tone: DebugTone;
  /** Chip content. */
  children: React.ReactNode;
  /** Optional tooltip. */
  title?: string;
  /** Optional accessible label (defaults to the visible content). */
  'aria-label'?: string;
  /** Additional CSS classes. */
  className?: string;
}

/** Semantic chip rendered through `Badge size="sm"`. */
export const DebugChip = React.memo(function DebugChip({
  tone,
  children,
  title,
  className,
  ...aria
}: DebugChipProps) {
  return (
    <Badge
      variant={badgeVariantFor(tone)}
      size="sm"
      title={title}
      aria-label={aria['aria-label']}
      className={cn('uppercase tracking-wide font-medium', className)}
    >
      {children}
    </Badge>
  );
});
