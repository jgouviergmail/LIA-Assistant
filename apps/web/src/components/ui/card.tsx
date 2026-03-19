import * as React from 'react';
import { cva, type VariantProps } from 'class-variance-authority';
import { cn } from '@/lib/utils';
import { type DomainAccent, DOMAIN_ACCENTS } from '@/constants/card';

/**
 * Card Component - Unified Design System
 *
 * Uses LIA design tokens for visual consistency with domain cards.
 * All shadows and radii use CSS variables from lia-components.css.
 *
 * @example
 * // Basic card
 * <Card>Content</Card>
 *
 * @example
 * // Status card with warning
 * <Card status="warning">Warning content</Card>
 *
 * @example
 * // Card with size (for usage without CardHeader/CardContent)
 * <Card size="lg">Content with padding</Card>
 *
 * @example
 * // Domain-specific accent
 * <Card domainAccent="email">Email content</Card>
 */
const cardVariants = cva(
  // Base: use LIA tokens for consistency with domain cards
  'rounded-[var(--lia-radius-lg)] border bg-card text-card-foreground transition-all duration-200',
  {
    variants: {
      // Visual variants (elevation/interaction)
      variant: {
        default: 'shadow-[var(--lia-shadow-sm)]',
        elevated: 'shadow-[var(--lia-shadow-md)] hover:shadow-[var(--lia-shadow-lg)]',
        interactive:
          'shadow-[var(--lia-shadow-sm)] hover:shadow-[var(--lia-shadow-md)] hover:border-primary/50 cursor-pointer',
        flat: 'shadow-none',
        gradient: 'bg-gradient-card shadow-[var(--lia-shadow-md)]',
      },
      // Semantic status variants (left border accent)
      status: {
        default: '',
        info: 'border-l-4 border-l-[var(--lia-info)] bg-[var(--lia-info-subtle)]',
        success: 'border-l-4 border-l-[var(--lia-success)] bg-[var(--lia-success-subtle)]',
        warning: 'border-l-4 border-l-[var(--lia-warning)] bg-[var(--lia-warning-subtle)]',
        error: 'border-l-4 border-l-[var(--lia-danger)] bg-[var(--lia-danger-subtle)]',
      },
      // Size variants (for usage WITHOUT CardHeader/CardContent)
      // Default is 'none' for backward compatibility (Card has no native padding)
      size: {
        none: '',
        sm: 'p-3',
        md: 'p-4',
        lg: 'p-6',
      },
    },
    defaultVariants: {
      variant: 'default',
      status: 'default',
      size: 'none',
    },
  }
);

/** Map domain to CSS variable class */
const domainAccentClasses: Record<DomainAccent, string> = Object.fromEntries(
  DOMAIN_ACCENTS.map(domain => [domain, `border-l-4 border-l-[var(--lia-${domain}-accent)]`])
) as Record<DomainAccent, string>;

export interface CardProps
  extends React.HTMLAttributes<HTMLDivElement>, VariantProps<typeof cardVariants> {
  /** Domain accent color for left border (email, contact, calendar, etc.) */
  domainAccent?: DomainAccent;
}

const Card = React.forwardRef<HTMLDivElement, CardProps>(
  ({ className, variant, status, size, domainAccent, ...props }, ref) => {
    const domainClass = domainAccent ? domainAccentClasses[domainAccent] : '';

    return (
      <div
        ref={ref}
        className={cn(cardVariants({ variant, status, size }), domainClass, className)}
        {...props}
      />
    );
  }
);
Card.displayName = 'Card';

const CardHeader = React.forwardRef<HTMLDivElement, React.HTMLAttributes<HTMLDivElement>>(
  ({ className, ...props }, ref) => (
    <div ref={ref} className={cn('flex flex-col space-y-1.5 p-6', className)} {...props} />
  )
);
CardHeader.displayName = 'CardHeader';

const CardTitle = React.forwardRef<HTMLDivElement, React.HTMLAttributes<HTMLDivElement>>(
  ({ className, ...props }, ref) => (
    <div
      ref={ref}
      className={cn('font-semibold leading-none tracking-tight', className)}
      {...props}
    />
  )
);
CardTitle.displayName = 'CardTitle';

const CardDescription = React.forwardRef<HTMLDivElement, React.HTMLAttributes<HTMLDivElement>>(
  ({ className, ...props }, ref) => (
    <div ref={ref} className={cn('text-sm text-muted-foreground', className)} {...props} />
  )
);
CardDescription.displayName = 'CardDescription';

const CardContent = React.forwardRef<HTMLDivElement, React.HTMLAttributes<HTMLDivElement>>(
  ({ className, ...props }, ref) => (
    <div ref={ref} className={cn('p-6 pt-0', className)} {...props} />
  )
);
CardContent.displayName = 'CardContent';

const CardFooter = React.forwardRef<HTMLDivElement, React.HTMLAttributes<HTMLDivElement>>(
  ({ className, ...props }, ref) => (
    <div ref={ref} className={cn('flex items-center p-6 pt-0', className)} {...props} />
  )
);
CardFooter.displayName = 'CardFooter';

export { Card, CardHeader, CardFooter, CardTitle, CardDescription, CardContent };
