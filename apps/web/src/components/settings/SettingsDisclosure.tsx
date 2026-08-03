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
        <span className="min-w-0 flex-1 truncate">{title}</span>
        {badge !== undefined && badge !== null && (
          <span className="shrink-0 rounded-full bg-muted px-2 py-0.5 text-xs tabular-nums text-muted-foreground">
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
