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
        // Success and destructive used to paint `green-100` / `red-100`, fixed
        // values that ignore the five colour themes and sit outside the
        // contrast guard — which reads `--color-*` pairs only. They were the
        // last two exceptions, and `lifecycleTone` routes most statuses to
        // them, so the exception was about to become the rule. The comment
        // that justified them ("solid opaque backgrounds to prevent gradient
        // bleed-through") described a risk that no longer exists: measured
        // 2026-08-05, `Card variant="gradient"` has zero call sites.
        success: 'bg-success/10 text-success border border-success/20 shadow-sm',
        destructive: 'bg-destructive/10 text-destructive border border-destructive/20 shadow-sm',
        warning: 'bg-warning/10 text-warning border border-warning/20 shadow-sm',
        // Alert: the only SOLID status ground. `destructive` and `warning` are
        // both pale tints (destructive/10 against warning/10), and their
        // tokens sit 23° apart in OKLCH hue — on screen "high" and "medium"
        // read as one level. Density is what separates them, and it keeps
        // working for a reader who cannot tell the two hues apart. Same token
        // pair as `Button variant="destructive"`, which the guard covers.
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
