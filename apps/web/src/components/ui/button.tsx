import * as React from 'react';
import { Slot } from '@radix-ui/react-slot';
import { cva, type VariantProps } from 'class-variance-authority';

import { cn } from '@/lib/utils';
import { LoadingSpinner } from './loading-spinner';

const buttonVariants = cva(
  'inline-flex items-center justify-center gap-2 whitespace-nowrap rounded-lg text-sm font-semibold transition-all duration-200 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 disabled:pointer-events-none disabled:opacity-60 [&_svg]:pointer-events-none [&_svg]:size-4 [&_svg]:shrink-0 btn-scale',
  {
    variants: {
      variant: {
        // Primary - Main action (soft blue)
        default:
          'bg-primary text-primary-foreground shadow-md hover:shadow-lg hover:bg-primary/90 active:scale-[0.98]',

        // Success - Positive actions (sage green)
        success:
          'bg-success text-success-foreground shadow-md hover:shadow-lg hover:bg-success/90 active:scale-[0.98]',

        // Warning - Warnings (coral orange)
        warning:
          'bg-warning text-warning-foreground shadow-md hover:shadow-lg hover:bg-warning/90 active:scale-[0.98]',

        // Destructive - Dangerous actions (terracotta)
        destructive:
          'bg-destructive text-destructive-foreground shadow-md hover:shadow-lg hover:bg-destructive/90 active:scale-[0.98]',

        // Secondary - Secondary actions (beige)
        secondary:
          'bg-secondary text-secondary-foreground shadow-sm hover:shadow-md hover:bg-secondary/80 active:scale-[0.98]',

        // Outline - Tertiary actions
        outline:
          'border-2 border-primary/30 bg-background text-primary shadow-sm hover:bg-primary/10 hover:border-primary hover:shadow-md active:scale-[0.98]',

        // Ghost - Subtle actions
        ghost: 'hover:bg-accent/50 hover:text-accent-foreground active:scale-[0.98]',

        // Link - Links
        link: 'text-primary underline-offset-4 hover:underline',

        // Soft variants - Soft versions of semantic colors
        softPrimary:
          'bg-primary/15 text-primary border-2 border-primary/25 hover:bg-primary/25 hover:border-primary/40 shadow-sm hover:shadow-md active:scale-[0.98]',

        softSuccess:
          'bg-success/15 text-success border-2 border-success/25 hover:bg-success/25 hover:border-success/40 shadow-sm hover:shadow-md active:scale-[0.98]',

        softWarning:
          'bg-warning/15 text-warning-foreground border-2 border-warning/25 hover:bg-warning/25 hover:border-warning/40 shadow-sm hover:shadow-md active:scale-[0.98]',
      },
      size: {
        default: 'h-9 px-4 py-2',
        sm: 'h-8 rounded-md px-3 text-xs',
        lg: 'h-11 rounded-md px-8 text-base',
        icon: 'h-9 w-9',
      },
    },
    defaultVariants: {
      variant: 'default',
      size: 'default',
    },
  }
);

export interface ButtonProps
  extends React.ButtonHTMLAttributes<HTMLButtonElement>,
    VariantProps<typeof buttonVariants> {
  asChild?: boolean;
  /** Shows loading spinner and disables button */
  isLoading?: boolean;
  /** Custom loading text (optional, no text shown if omitted) */
  loadingText?: string;
}

const Button = React.forwardRef<HTMLButtonElement, ButtonProps>(
  ({ className, variant, size, asChild = false, isLoading, loadingText, children, disabled, ...props }, ref) => {
    const Comp = asChild ? Slot : 'button';
    return (
      <Comp
        className={cn(buttonVariants({ variant, size, className }))}
        ref={ref}
        disabled={disabled || isLoading}
        {...props}
      >
        {isLoading ? (
          <>
            <LoadingSpinner size="default" label={loadingText} />
            {loadingText}
          </>
        ) : (
          children
        )}
      </Comp>
    );
  }
);
Button.displayName = 'Button';

export { Button, buttonVariants };
