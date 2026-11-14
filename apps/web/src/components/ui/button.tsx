'use client';

import * as React from 'react';
import { Slot } from '@radix-ui/react-slot';
import type { VariantProps } from 'class-variance-authority';
import { buttonVariants } from './button-variants';

import { cn } from '@/lib/utils';
import { Loader2 } from '@/lib/icons';
import { MonochromeIcons } from '@/lib/icon-style-context';

type ButtonVariant = NonNullable<VariantProps<typeof buttonVariants>['variant']>;

/** The variants painting a solid colour behind their label: their glyphs follow the label. */
const SOLID_VARIANTS: ReadonlySet<ButtonVariant> = new Set([
  'default',
  'success',
  'warning',
  'destructive',
]);

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
    const button = (
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
    return (
      <MonochromeIcons enabled={SOLID_VARIANTS.has(variant ?? 'default')}>{button}</MonochromeIcons>
    );
  }
);
Button.displayName = 'Button';

export { Button, buttonVariants };
