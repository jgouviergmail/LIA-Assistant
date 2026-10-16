'use client';

import * as React from 'react';
import { Slot } from '@radix-ui/react-slot';
import type { VariantProps } from 'class-variance-authority';
import { buttonVariants } from './button-variants';

import { cn } from '@/lib/utils';
import { Loader2 } from 'lucide-react';

export interface ButtonProps
  extends React.ButtonHTMLAttributes<HTMLButtonElement>, VariantProps<typeof buttonVariants> {
  asChild?: boolean;
  /** Keeps the label and focus while guarding repeated activation. */
  isLoading?: boolean;
  /** Optional accessible description during loading; the label stays stable. */
  loadingText?: string;
}

const Button = React.forwardRef<HTMLButtonElement, ButtonProps>(
  (
    {
      className,
      variant,
      size,
      asChild = false,
      isLoading,
      loadingText,
      children,
      disabled,
      onClick,
      onClickCapture,
      ...props
    },
    ref
  ) => {
    const Comp = asChild ? Slot : 'button';
    return (
      <Comp
        className={cn(buttonVariants({ variant, size, className }))}
        ref={ref}
        {...props}
        disabled={disabled}
        aria-disabled={
          isLoading ? true : (props['aria-disabled'] ?? (asChild && disabled ? true : undefined))
        }
        aria-busy={isLoading ? true : props['aria-busy']}
        aria-description={isLoading && loadingText ? loadingText : props['aria-description']}
        onClickCapture={event => {
          if (isLoading || disabled) {
            event.preventDefault();
            event.stopPropagation();
            return;
          }
          onClickCapture?.(event);
        }}
        onClick={event => {
          if (!isLoading && !disabled) onClick?.(event);
        }}
      >
        {asChild ? (
          children
        ) : (
          <>
            {children}
            {isLoading && (
              <Loader2 className="absolute right-0.5 !size-2.5 animate-spin" aria-hidden="true" />
            )}
          </>
        )}
      </Comp>
    );
  }
);
Button.displayName = 'Button';

export { Button, buttonVariants };
