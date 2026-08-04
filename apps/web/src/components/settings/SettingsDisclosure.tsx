'use client';

import { ChevronDown, type LucideIcon } from 'lucide-react';
import { useState, type ReactNode } from 'react';

import { cn } from '@/lib/utils';

/**
 * A folded sub-block inside a settings section.
 *
 * The proactivity panel stacks a frequency form, eleven source switches and a
 * ten-row history. Shown at once that is a wall, and the reader came to change
 * one thing. Each block folds, and folds CLOSED: the section becomes an index
 * you open rather than a page you scroll past — the same reasoning as the 360°
 * relationship card, where the count on the toggle is what you choose from
 * while everything is shut.
 *
 * **Native `<details>`, not a div with a handler.** The disclosure semantics,
 * the keyboard behaviour and the open/closed announcement come from the
 * platform. `UsageStatistics` and the public FAQ already do this; a bespoke
 * toggle would owe all three by hand and get one of them wrong.
 *
 * **Closed means unmounted, not merely hidden.** A `<details>` keeps its
 * content in the DOM, so a hook inside it would still run and still fetch. The
 * children render only while open, which is what lets a collapsed history cost
 * nothing — and what makes `onOpenChange` enough to gate a query.
 */
export interface SettingsDisclosureProps {
  icon: LucideIcon;
  /** Already translated — this shell never resolves a key itself. */
  title: string;
  /** Usually the exact total; rendered inside the summary, next to the title. */
  badge?: ReactNode;
  /**
   * Palette of the badge pill, as theme-token classes.
   *
   * Defaults to the neutral muted pill. A caller passes this when the count
   * itself carries meaning — "this section holds something" reads at a glance
   * when it is tinted and its empty neighbour is not. Classes rather than a
   * nested `<Badge>`: this component already IS the pill, and wrapping one in
   * the other nested two backgrounds (measured 2026-08-04).
   */
  badgeClassName?: string;
  /**
   * One line under the title, visible WHILE FOLDED.
   *
   * A folded block is an index entry: what it holds has to be readable before
   * opening it, or the reader opens each one to find out — which is exactly
   * the scanning the fold exists to spare them. Outside the `<summary>` it
   * would be unmounted with the children and only appear once open, i.e. once
   * it is no longer needed.
   */
  description?: string;
  /** Open on arrival. Default false, deliberately. */
  defaultOpen?: boolean;
  /** Notified on every state change, so a caller can enable its query. */
  onOpenChange?: (open: boolean) => void;
  className?: string;
  children: ReactNode;
}

export function SettingsDisclosure({
  icon: Icon,
  title,
  badge,
  badgeClassName,
  description,
  defaultOpen = false,
  onOpenChange,
  className,
  children,
}: SettingsDisclosureProps) {
  const [open, setOpen] = useState(defaultOpen);

  return (
    <details
      className={cn('group rounded-lg border border-border/40 bg-card/40 px-3', className)}
      // Fully controlled: React and the DOM always agree. Passing the
      // CONSTANT `defaultOpen` here would work only by accident — React skips
      // an unchanged prop, so the element the user opened keeps its attribute
      // while the vdom still believes it shut. One day a re-render disagrees
      // and the block closes under the reader's finger.
      open={open}
      onToggle={event => {
        const next = (event.currentTarget as HTMLDetailsElement).open;
        setOpen(next);
        onOpenChange?.(next);
      }}
    >
      {/* `list-none` removes the native marker; the chevron replaces it and
          rotates with `group-open`. The summary is the toggle, so the focus
          ring belongs here. */}
      <summary
        className={cn(
          'flex cursor-pointer list-none items-center gap-2 py-2.5 text-sm font-medium',
          'text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring',
          'rounded-lg'
        )}
      >
        <Icon className="h-4 w-4 shrink-0 text-primary" aria-hidden="true" />
        <span className="min-w-0 flex-1">
          <span className="block truncate">{title}</span>
          {description && (
            <span className="block text-xs font-normal text-muted-foreground">{description}</span>
          )}
        </span>
        {badge !== undefined && badge !== null && (
          <span
            className={cn(
              'shrink-0 rounded-full px-2 py-0.5 text-xs font-medium tabular-nums',
              badgeClassName ?? 'bg-muted text-muted-foreground'
            )}
          >
            {badge}
          </span>
        )}
        <ChevronDown
          className="h-4 w-4 shrink-0 text-muted-foreground transition-transform group-open:rotate-180 motion-reduce:transition-none"
          aria-hidden="true"
        />
      </summary>
      {open && <div className="pb-3">{children}</div>}
    </details>
  );
}
