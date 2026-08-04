/**
 * LoadingSpinner - Reusable loading indicator component.
 *
 * Standardizes the spinner pattern used across the application.
 * Built on top of Lucide's Loader2 icon with animation.
 */

'use client';

import * as React from 'react';
import { Loader2 } from 'lucide-react';
import { useTranslation } from 'react-i18next';
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
      // The semantic token, not `text-green-500`: a raw palette value ignores
      // the five colour themes and sits outside the contrast guard, which
      // only covers `--color-*` pairs.
      success: 'text-success',
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
  /**
   * Screen-reader label. Defaults to the active locale's `common.loading` —
   * never to an English literal, which the ~90 call sites that omit this prop
   * would otherwise announce in every language.
   */
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
  label,
  ...props
}: LoadingSpinnerProps) {
  const { t } = useTranslation();

  return (
    <Loader2
      className={cn(spinnerVariants({ size, spinnerColor }), className)}
      aria-label={label ?? t('common.loading')}
      role="status"
      {...props}
    />
  );
}
