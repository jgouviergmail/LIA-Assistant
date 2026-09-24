'use client';

import { useId, useState, useSyncExternalStore } from 'react';
import { ChevronRight } from 'lucide-react';
import { cn } from '@/lib/utils';

/**
 * Reading level 2 of the editorial landing: the catalog under each chapter
 * (and the basics band). It is FOLDED on arrival — owner arbitration
 * 2026-09-24, superseding "open on arrival": the page reads as a sequence of
 * chapters, and each catalog is one click away for the reader who wants the
 * detail. Collapsed content stays in the DOM either way, so search engines
 * index every description.
 *
 * The anchor makes the unfolded state deep-linkable: a URL whose hash names it
 * (`/#c1-detail`) opens the catalog, on arrival and whenever the hash later
 * moves there. The reader's own toggle wins until the hash moves again.
 *
 * Native button + aria-expanded/aria-controls; the grid collapses via the
 * CSS `grid-template-rows` trick (animatable, no JS measurement).
 */

export interface CatalogDisclosureProps {
  /** Translated summary label, e.g. "Everything LIA can do here". */
  summary: string;
  /** Translated hint after the summary (item count / content list). */
  hint?: string;
  /** Anchor id: a URL hash naming it unfolds the catalog. */
  anchor?: string;
  children: React.ReactNode;
}

function subscribeToHash(onChange: () => void): () => void {
  window.addEventListener('hashchange', onChange);
  return () => window.removeEventListener('hashchange', onChange);
}

const readHash = (): string => window.location.hash;
// The server has no URL fragment: every catalog renders folded, and the client
// opens the targeted one right after hydration.
const readServerHash = (): string => '';

/** The reader's last toggle, and the hash it was made under. */
interface Toggle {
  hash: string;
  open: boolean;
}

/** A hash newly pointing at the catalog opens it; otherwise the reader's last choice stands. */
function resolveOpen(targeted: boolean, toggle: Toggle | null, hash: string): boolean {
  if (toggle === null) return targeted;
  if (targeted && toggle.hash !== hash) return true;
  return toggle.open;
}

export function CatalogDisclosure({ summary, hint, anchor, children }: CatalogDisclosureProps) {
  const hash = useSyncExternalStore(subscribeToHash, readHash, readServerHash);
  const [toggle, setToggle] = useState<Toggle | null>(null);
  const panelId = useId();

  const open = resolveOpen(anchor !== undefined && hash === `#${anchor}`, toggle, hash);

  return (
    <div id={anchor} className="mt-10">
      <button
        type="button"
        aria-expanded={open}
        aria-controls={panelId}
        onClick={() => setToggle({ hash, open: !open })}
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
