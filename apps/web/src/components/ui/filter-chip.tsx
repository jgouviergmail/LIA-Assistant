'use client';

import type { LucideIcon } from '@/lib/icons';
import { cn } from '@/lib/utils';

/** A quick list filter with native toggle-button semantics. */
export function FilterChip({
  active,
  label,
  icon: Icon,
  onToggle,
}: {
  active: boolean;
  label: string;
  icon: LucideIcon;
  onToggle: () => void;
}) {
  return (
    <button
      type="button"
      onClick={onToggle}
      aria-pressed={active}
      className={cn(
        'inline-flex min-h-11 max-w-full items-center justify-center gap-1.5 rounded-full border px-3 py-2 text-sm font-medium transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring',
        active
          ? 'border-primary/40 bg-primary/10 text-primary'
          : 'border-border text-muted-foreground hover:bg-muted/60'
      )}
    >
      <Icon className="h-4 w-4 shrink-0" aria-hidden="true" />
      {label}
    </button>
  );
}
