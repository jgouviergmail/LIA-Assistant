import * as React from 'react';
import { cva, type VariantProps } from 'class-variance-authority';
import { cn } from '@/lib/utils';

const infoBoxVariants = cva('rounded-lg border p-3', {
  variants: {
    variant: {
      default: 'border-border bg-muted/30',
      warning: 'border-yellow-500/20 bg-yellow-500/5',
      error: 'border-red-500/20 bg-red-500/5',
    },
  },
  defaultVariants: {
    variant: 'default',
  },
});

export interface InfoBoxProps
  extends React.HTMLAttributes<HTMLDivElement>,
    VariantProps<typeof infoBoxVariants> {}

/**
 * InfoBox component for displaying informational, warning, or error messages.
 *
 * Replaces the duplicated pattern:
 * <div className="rounded-lg border border-border bg-muted/30 p-3">
 *   <p className="text-xs text-muted-foreground">{text}</p>
 * </div>
 *
 * @example
 * // Simple text
 * <InfoBox>
 *   <p className="text-xs text-muted-foreground">Your info text here</p>
 * </InfoBox>
 *
 * // Warning variant
 * <InfoBox variant="warning">
 *   <p className="text-xs text-yellow-700 dark:text-yellow-400">Warning message</p>
 * </InfoBox>
 *
 * // Error variant
 * <InfoBox variant="error">
 *   <p className="text-xs text-red-700 dark:text-red-400">Error message</p>
 * </InfoBox>
 *
 * // Complex content
 * <InfoBox className="space-y-2">
 *   <p className="text-xs font-medium">Title</p>
 *   <p className="text-xs text-muted-foreground">Description</p>
 * </InfoBox>
 */
function InfoBox({ className, variant, children, ...props }: InfoBoxProps) {
  return (
    <div className={cn(infoBoxVariants({ variant }), className)} {...props}>
      {children}
    </div>
  );
}

export { InfoBox, infoBoxVariants };
