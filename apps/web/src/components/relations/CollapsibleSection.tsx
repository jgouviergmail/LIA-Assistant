'use client';

/**
 * CollapsibleSection — the one section shell of the 360° view.
 *
 * A relationship card stacks up to eight sections; without folding, the page
 * becomes a scroll no one reads to the end. Every section therefore collapses,
 * and the shell is shared so the database-local ones and the provider-backed
 * ones cannot drift into two visual languages.
 *
 * **Closed by default.** The reader lands on a compact index of the
 * relationship — every heading with its exact count — and opens what they came
 * for, instead of scrolling past seven sections to reach the eighth. This is
 * why the count belongs on the toggle and not inside the panel: folded, the
 * badge is the only thing left to choose from.
 *
 * Accessibility contract, deliberately native:
 *
 * - the toggle is a real `button` carrying `aria-expanded` and `aria-controls`,
 *   so a screen reader announces the state and the relationship;
 * - the accessible NAME is the section title, translated — never an icon alone;
 * - the panel keeps its `id` whether open or closed (an `aria-controls` that
 *   points at nothing is worse than none);
 * - a per-section action (refresh) sits OUTSIDE the toggle: a button inside a
 *   button is invalid HTML and unreachable by keyboard.
 */

import { useId, useState } from 'react';
import { ChevronDown, type LucideIcon } from 'lucide-react';

import { cn } from '@/lib/utils';

export function CollapsibleSection({
  icon: Icon,
  title,
  badge,
  action,
  defaultOpen = false,
  className,
  children,
}: {
  icon: LucideIcon;
  title: string;
  /** Usually the exact total — rendered inside the toggle, next to the title. */
  badge?: React.ReactNode;
  /** Rendered next to the toggle, never inside it. */
  action?: React.ReactNode;
  /** Closed by default — the panel is an index the reader opens, not a wall. */
  defaultOpen?: boolean;
  className?: string;
  children: React.ReactNode;
}) {
  const [open, setOpen] = useState(defaultOpen);
  const panelId = useId();

  return (
    <section className={cn('rounded-xl border border-border/50 bg-card p-4', className)}>
      <div className="flex items-center justify-between gap-1">
        <h3 className="min-w-0 flex-1 text-sm font-semibold text-foreground">
          <button
            type="button"
            onClick={() => setOpen(value => !value)}
            aria-expanded={open}
            aria-controls={panelId}
            className="flex min-h-11 w-full flex-wrap items-center gap-2 rounded-md py-1 text-left focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
          >
            <Icon className="h-4 w-4 shrink-0 text-primary" aria-hidden="true" />
            {title}
            {badge}
            <ChevronDown
              aria-hidden="true"
              className={cn(
                'h-4 w-4 shrink-0 text-muted-foreground transition-transform',
                !open && '-rotate-90'
              )}
            />
          </button>
        </h3>
        {action}
      </div>
      {/* The id survives the fold: `aria-controls` must always resolve. */}
      <div id={panelId} hidden={!open} className="mt-3 space-y-2.5">
        {children}
      </div>
    </section>
  );
}

/**
 * The count pill shared by every section that has an exact total.
 *
 * The primary tint, like every other badge in the app: grey read as
 * decoration next to headings that are themselves grey, and a count is
 * information — it is what tells the reader whether a folded section is worth
 * opening. Same ground and border as `Badge variant="default"`, kept as a
 * local span because this one lives inside a `<summary>` and must not inherit
 * the badge's own height.
 */
export function SectionBadge({ children }: { children: React.ReactNode }) {
  return (
    <span className="rounded-full border border-primary/20 bg-primary/10 px-2 py-px text-[11px] font-medium tabular-nums text-primary">
      {children}
    </span>
  );
}
