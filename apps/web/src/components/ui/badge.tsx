import * as React from 'react';
import { cva, type VariantProps } from 'class-variance-authority';
import { cn } from '@/lib/utils';

const badgeVariants = cva(
  'inline-flex items-center gap-1.5 rounded-full px-2.5 py-0.5 text-xs font-semibold transition-all duration-200',
  {
    variants: {
      variant: {
        default: 'bg-primary/10 text-primary border border-primary/20 shadow-sm',
        secondary: 'bg-secondary text-secondary-foreground border border-border',
        // Success: solid opaque backgrounds to prevent gradient bleed-through
        success:
          'bg-green-100 text-green-800 dark:bg-green-900 dark:text-green-200 border border-green-200 dark:border-green-800 shadow-sm',
        // Destructive: solid opaque backgrounds to prevent gradient bleed-through
        destructive:
          'bg-red-100 text-red-800 dark:bg-red-900 dark:text-red-200 border border-red-200 dark:border-red-800 shadow-sm',
        warning: 'bg-warning/10 text-warning border border-warning/20 shadow-sm',
        // Alert: the only SOLID status ground. `destructive` and `warning` are
        // both pale tints (red-100 against warning/10), and their tokens sit
        // 23° apart in OKLCH hue — on screen "high" and "medium" read as one
        // level. Density is what separates them, and it keeps working for a
        // reader who cannot tell the two hues apart. Same token pair as
        // `Button variant="destructive"`, which the contrast guard covers.
        alert: 'bg-destructive text-destructive-foreground border border-destructive shadow-sm',
        info: 'bg-primary/10 text-primary border border-primary/20 shadow-sm',
        outline: 'border border-input bg-background hover:bg-accent hover:text-accent-foreground',
        ghost: 'hover:bg-accent hover:text-accent-foreground',
      },
      size: {
        default: 'h-5',
        sm: 'h-4 text-[10px] px-2',
        lg: 'h-6 text-sm px-3',
      },
    },
    defaultVariants: {
      variant: 'default',
      size: 'default',
    },
  }
);

export interface BadgeProps
  extends React.HTMLAttributes<HTMLDivElement>, VariantProps<typeof badgeVariants> {
  icon?: React.ReactNode;
  pulse?: boolean;
}

function Badge({ className, variant, size, icon, pulse, children, ...props }: BadgeProps) {
  return (
    <div className={cn(badgeVariants({ variant, size }), className)} {...props}>
      {pulse && (
        <span className="relative flex h-2 w-2">
          <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-current opacity-75"></span>
          <span className="relative inline-flex rounded-full h-2 w-2 bg-current"></span>
        </span>
      )}
      {icon && <span className="inline-flex">{icon}</span>}
      {children}
    </div>
  );
}

export { Badge, badgeVariants };
