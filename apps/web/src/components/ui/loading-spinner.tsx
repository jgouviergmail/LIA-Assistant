/**
 * LoadingSpinner - Reusable loading indicator component.
 *
 * Standardizes the spinner pattern used across the application.
 * Built on top of Lucide's Loader2 icon with animation.
 */

import * as React from 'react';
import { Loader2 } from 'lucide-react';
import { cn } from '@/lib/utils';
import { cva, type VariantProps } from 'class-variance-authority';

const spinnerVariants = cva('animate-spin', {
  variants: {
    size: {
      sm: 'h-3 w-3',
      default: 'h-4 w-4',
      md: 'h-5 w-5',
      lg: 'h-6 w-6',
      xl: 'h-8 w-8',
      '2xl': 'h-16 w-16',
    },
    spinnerColor: {
      default: 'text-primary',
      muted: 'text-muted-foreground',
      success: 'text-green-500',
      destructive: 'text-destructive',
      white: 'text-white',
    },
  },
  defaultVariants: {
    size: 'default',
    spinnerColor: 'default',
  },
});

export interface LoadingSpinnerProps
  extends Omit<React.SVGProps<SVGSVGElement>, 'ref'>, VariantProps<typeof spinnerVariants> {
  /** Optional label for screen readers */
  label?: string;
}

/**
 * Loading spinner component.
 *
 * Usage:
 * ```tsx
 * // Basic usage
 * <LoadingSpinner />
 *
 * // With size variant
 * <LoadingSpinner size="lg" />
 *
 * // With color variant
 * <LoadingSpinner spinnerColor="muted" />
 *
 * // In a button
 * <Button disabled={loading}>
 *   {loading ? <LoadingSpinner size="sm" spinnerColor="white" /> : 'Submit'}
 * </Button>
 * ```
 */
export function LoadingSpinner({
  className,
  size,
  spinnerColor,
  label = 'Loading...',
  ...props
}: LoadingSpinnerProps) {
  return (
    <Loader2
      className={cn(spinnerVariants({ size, spinnerColor }), className)}
      aria-label={label}
      role="status"
      {...props}
    />
  );
}
