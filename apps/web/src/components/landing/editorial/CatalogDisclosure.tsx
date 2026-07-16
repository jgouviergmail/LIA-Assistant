'use client';

import { useId, useState } from 'react';
import { ChevronRight } from 'lucide-react';
import { cn } from '@/lib/utils';

/**
 * Reading level 2 of the editorial landing: the expandable catalog under each
 * chapter (and the basics band). The narrative stays light on scroll; one
 * click reveals the full detailed feature cards — which remain in the DOM
 * while collapsed, so search engines index every description.
 *
 * Native button + aria-expanded/aria-controls; the grid collapses via the
 * CSS `grid-template-rows` trick (animatable, no JS measurement).
 */

export interface CatalogDisclosureProps {
  /** Translated summary label, e.g. "Everything she can do here". */
  summary: string;
  /** Translated hint after the summary (item count / content list). */
  hint?: string;
  /** Anchor id so the expanded state is deep-linkable. */
  anchor?: string;
  children: React.ReactNode;
}

export function CatalogDisclosure({ summary, hint, anchor, children }: CatalogDisclosureProps) {
  const [open, setOpen] = useState(false);
  const panelId = useId();

  return (
    <div id={anchor} className="mt-10">
      <button
        type="button"
        aria-expanded={open}
        aria-controls={panelId}
        onClick={() => setOpen(v => !v)}
        className="flex w-full items-center gap-3 rounded-xl border border-border bg-card px-5 py-3.5 text-left transition-colors hover:border-primary/40 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
      >
        <ChevronRight
          aria-hidden="true"
          className={cn(
            'h-4 w-4 shrink-0 text-primary transition-transform duration-200',
            open && 'rotate-90'
          )}
        />
        <span className="text-sm font-semibold">{summary}</span>
        {hint && (
          <span className="ml-auto hidden text-xs font-normal text-muted-foreground sm:block">
            {hint}
          </span>
        )}
      </button>
      <div
        id={panelId}
        className={cn(
          'grid transition-[grid-template-rows] duration-300 ease-out motion-reduce:transition-none',
          open ? 'grid-rows-[1fr]' : 'grid-rows-[0fr]'
        )}
      >
        {/* inert while collapsed: content stays indexable but untabbable */}
        <div className="overflow-hidden" {...(open ? {} : { inert: true })}>
          <div className="pt-4">{children}</div>
        </div>
      </div>
    </div>
  );
}
