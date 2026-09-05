'use client';

/**
 * The body both transparency registers share (ADR-263, lot 4).
 *
 * Everything below the header is the same in the two journals: the error
 * banner, the first-load skeleton, the `aria-busy` container, the exact total,
 * the two kinds of emptiness, the list and the load-more footer. What differs
 * is the filter controls and how ONE row is drawn — so those are the two
 * things a caller passes in.
 *
 * This is also what keeps the complexity ratchet honest: the branching lives
 * here once rather than twice, and each journal keeps only the decisions that
 * are its own. The ratchet is shrink-only; the answer to a hotspot is
 * decomposition, never a raised cap.
 *
 * Loading rules (charter): first load → skeleton geometry matching the real
 * list, with one announcement; refresh of a populated list → `aria-busy`,
 * never an unmount; `no-data` and `no-match` are DIFFERENT emptinesses.
 */

import type { ReactNode } from 'react';
import type { LucideIcon } from 'lucide-react';

import {
  RegisterError,
  RegisterLoadMore,
  RegisterSkeleton,
} from '@/components/effects/RegisterJournalStates';
import { Badge } from '@/components/ui/badge';
import { EmptyState } from '@/components/ui/empty-state';
import type { UseRegisterJournalResult } from '@/hooks/useRegisterJournal';

export interface RegisterEmptyCopy {
  icon: LucideIcon;
  title: string;
  description: string;
  /** `no-data`: nothing was ever recorded. `no-match`: the filter excluded it. */
  reason: 'no-data' | 'no-match';
  action: { label: string; href: string };
}

export interface RegisterJournalBodyProps<
  TEntry extends { id: string },
  TItem extends { id: string } = TEntry,
> {
  /** Everything the reading hook returned. */
  state: UseRegisterJournalResult<TEntry>;
  /** Identifies which register is loading, for the geometry oracle. */
  skeletonSlot: string;
  errorMessage: string;
  retryLabel: string;
  /** The exact total, already interpolated. Absent before the first payload. */
  totalLabel?: string;
  /** The register's own filter controls, when it has any. */
  filters?: ReactNode;
  empty: RegisterEmptyCopy;
  loadMoreLabel: string;
  /**
   * The item's day, in the READER's timezone, already formatted by the caller
   * — which owns the `Intl` formatter and therefore the locale. Two entries
   * sharing a value sit under one heading.
   */
  dayOf: (item: TItem) => string;
  renderRow: (item: TItem) => ReactNode;
  /**
   * What to DISPLAY, from what the server returned. Required rather than
   * optional so the two types stay honest without a cast: the consultation
   * register folds consecutive identical calls into one line, the action
   * register passes its entries through (`entries => entries`).
   */
  itemsOf: (entries: TEntry[]) => TItem[];
}

/** One day's worth of rows, in the order they arrived. */
interface DaySection<TItem> {
  day: string;
  items: TItem[];
}

/**
 * Split a list into consecutive same-day sections.
 *
 * Consecutive rather than grouped-by-key on purpose: the journal is ordered by
 * time, so a same-day run is contiguous, and re-bucketing would silently
 * reorder a list whose order is its meaning.
 */
function byDay<TItem extends { id: string }>(
  items: TItem[],
  dayOf: (item: TItem) => string
): DaySection<TItem>[] {
  const sections: DaySection<TItem>[] = [];
  for (const item of items) {
    const day = dayOf(item);
    const last = sections[sections.length - 1];
    if (last && last.day === day) {
      last.items.push(item);
    } else {
      sections.push({ day, items: [item] });
    }
  }
  return sections;
}

export function RegisterJournalBody<
  TEntry extends { id: string },
  TItem extends { id: string } = TEntry,
>({
  state,
  skeletonSlot,
  errorMessage,
  retryLabel,
  totalLabel,
  filters,
  empty,
  loadMoreLabel,
  dayOf,
  renderRow,
  itemsOf,
}: RegisterJournalBodyProps<TEntry, TItem>) {
  const { entries, hasMore, firstLoad, loading, error, loadMore, refetch } = state;

  if (error && entries === undefined) {
    return <RegisterError message={errorMessage} retryLabel={retryLabel} onRetry={refetch} />;
  }
  if (firstLoad) {
    return <RegisterSkeleton slot={skeletonSlot} />;
  }

  const visible = itemsOf(entries ?? []);
  const sections = byDay(visible, dayOf);
  return (
    <div aria-busy={loading || undefined} className="space-y-6">
      <div className="flex flex-wrap items-center gap-2">
        {totalLabel !== undefined && <Badge variant="default">{totalLabel}</Badge>}
        {filters}
      </div>

      {visible.length === 0 ? (
        <EmptyState
          variant="page"
          icon={empty.icon}
          title={empty.title}
          description={empty.description}
          reason={empty.reason}
          action={empty.action}
        />
      ) : (
        <div className="space-y-6">
          {sections.map(section => (
            <section key={section.day} className="space-y-2">
              {/* A real heading, not a styled row: a screen reader then gets
                  the journal's outline, and the day is reachable by heading
                  navigation like every other section of the app. */}
              <h3 className="flex items-center gap-3 text-xs font-semibold uppercase tracking-wide text-muted-foreground">
                <span className="shrink-0">{section.day}</span>
                <span aria-hidden="true" className="h-px flex-1 bg-border" />
              </h3>
              <ul className="space-y-2">{section.items.map(renderRow)}</ul>
            </section>
          ))}
          {hasMore && (
            <RegisterLoadMore
              label={loadMoreLabel}
              busy={loading && !firstLoad}
              onLoadMore={loadMore}
            />
          )}
        </div>
      )}
    </div>
  );
}
