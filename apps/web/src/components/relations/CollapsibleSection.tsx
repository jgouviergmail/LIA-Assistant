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
import { ChevronDown, RefreshCw, type LucideIcon } from 'lucide-react';

import { cn } from '@/lib/utils';
import { Card } from '@/components/ui/card';

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
    <section>
      <Card className={cn('border-border p-4', className)}>
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
              <span className="min-w-0 flex-1 break-words">{title}</span>
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
      </Card>
    </section>
  );
}

/**
 * A section's items as plain rows split by a hairline — the rhythm of the
 * Alerts timeline (owner request 2026-10-21): a nested card per item drew a
 * panel inside a panel. A real list, so a screen reader counts the items.
 */
export function SectionRows({ children }: { children: React.ReactNode }) {
  return (
    <ul role="list" className="min-w-0">
      {children}
    </ul>
  );
}

/**
 * A row's title line: its markers, then WHEN (`RelationWhen`) — the mail rows'
 * line, which every dated row of the card shares (owner request 2026-10-21).
 * A flex line, so the 11px phrase sets its height rather than the inherited
 * body text's strut. It owns the 6px gap to the content below, so no row
 * restates it — the mail rows and the SMS keep the same 6px (owner request
 * 2026-10-21: two pixels read as one cramped block).
 */
export function SectionRowTitle({ children }: { children: React.ReactNode }) {
  return <p className="mb-1.5 flex flex-wrap items-baseline gap-2">{children}</p>;
}

/** One row of `SectionRows`; an interactive row passes its own padding. */
export function SectionRow({
  className,
  children,
}: {
  className?: string;
  children: React.ReactNode;
}) {
  return (
    <li className={cn('min-w-0 border-b border-border py-3 last:border-b-0', className)}>
      {children}
    </li>
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
    <span className="rounded-full border border-primary/20 bg-primary/10 px-2 py-px text-px-11 font-medium tabular-nums text-primary">
      {children}
    </span>
  );
}

/**
 * The refresh control a section carries, wherever the section lives.
 *
 * Hoisted here from the provider sections when the debrief grew one too: two
 * "look again" buttons on one card, drawn differently, would read as two
 * different promises. This is the card's ONE refresh affordance.
 *
 * `aria-disabled`, never `disabled`: a control disabled while focused is
 * blurred by the browser and leaves the tab order, so a keyboard reader is
 * thrown back to the document (ADR-206). The GUARD in the handler is what
 * prevents the second press.
 */
export function RefreshButton({
  label,
  busy,
  onRefresh,
}: {
  label: string;
  busy: boolean;
  onRefresh: () => void;
}) {
  return (
    <button
      type="button"
      onClick={() => {
        if (!busy) onRefresh();
      }}
      aria-disabled={busy}
      aria-label={label}
      title={label}
      className={cn(
        'shrink-0 inline-flex min-h-11 min-w-11 items-center justify-center rounded-md text-muted-foreground transition-colors hover:bg-muted/60 hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring',
        busy && 'cursor-not-allowed opacity-50'
      )}
    >
      <RefreshCw className={cn('h-3.5 w-3.5', busy && 'animate-spin')} aria-hidden="true" />
    </button>
  );
}
