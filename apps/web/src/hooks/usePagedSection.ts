'use client';

/**
 * One paginated, foldable section of the notifications hub.
 *
 * The hub stacks five of them and every one answers the same question the same
 * way: a bounded page, the EXACT total behind it (ADR-185), a first-load
 * spinner that a refetch must not bring back, and no request at all while the
 * section is closed. Written five times, the fifth copy is where one of those
 * four rules would quietly go missing.
 *
 * Two rules are load-bearing and easy to get wrong:
 *
 * - `firstLoad` is derived from the ABSENCE of data, never from `error`: a
 *   refetch clears the error, and a spinner keyed on it unmounts the list
 *   mid-refresh (the defect measured on `PeerConnectionsSettings`, 2026-07-31);
 * - the page resets to 1 whenever the section is closed, so re-opening it
 *   never lands on page 4 of a list the reader last saw days ago.
 */

import { useCallback, useState } from 'react';

import { useApiQuery } from './useApiQuery';

/** Rows per page across the whole hub — one number, one reading rhythm. */
export const HUB_PAGE_SIZE = 10;

export interface PagedSection<TItem> {
  items: TItem[] | undefined;
  /** EXACT count over the whole set, not the length of this page. */
  total: number;
  /** 1-indexed, as the pagination control expects. */
  page: number;
  setPage: (page: number) => void;
  totalPages: number;
  /** True only before the first payload — never on a refetch. */
  firstLoad: boolean;
  loading: boolean;
  error: Error | null;
  refetch: () => void;
}

export interface UsePagedSectionOptions<TPayload, TItem> {
  /** Endpoint WITHOUT its paging query — the hook owns `limit`/`offset`. */
  path: string;
  /** Pull the rows out of the payload. */
  selectItems: (payload: TPayload) => TItem[];
  /** Pull the exact total out of the payload. */
  selectTotal: (payload: TPayload) => number;
  /** Fetch only while the section is open: a folded list costs nothing. */
  enabled: boolean;
  pageSize?: number;
}

export function usePagedSection<TPayload, TItem>({
  path,
  selectItems,
  selectTotal,
  enabled,
  pageSize = HUB_PAGE_SIZE,
}: UsePagedSectionOptions<TPayload, TItem>): PagedSection<TItem> {
  const [page, setPage] = useState(1);

  // Closing the section forgets the position. Re-opening on page 4 of a list
  // the reader last saw days ago would be a state nobody asked to keep.
  //
  // Adjusted DURING RENDER (the official React pattern for "state that depends
  // on a prop"), never in an effect: an effect would render page 4 once, paint
  // it, then correct itself — and the ratchet refuses `setState` in an effect
  // precisely because that flash is a real one. React discards this render and
  // immediately re-runs with the new state, so nothing reaches the screen.
  const [wasEnabled, setWasEnabled] = useState(enabled);
  if (wasEnabled !== enabled) {
    setWasEnabled(enabled);
    if (!enabled) setPage(1);
  }

  const separator = path.includes('?') ? '&' : '?';
  const { data, loading, error, refetch } = useApiQuery<TPayload>(
    `${path}${separator}limit=${pageSize}&offset=${(page - 1) * pageSize}`,
    { componentName: 'usePagedSection', enabled }
  );

  const total = data ? selectTotal(data) : 0;
  const items = data ? selectItems(data) : undefined;

  const goTo = useCallback((next: number) => setPage(Math.max(1, next)), []);

  return {
    items,
    total,
    page,
    setPage: goTo,
    totalPages: Math.max(1, Math.ceil(total / pageSize)),
    // Derived from `data`, never from `error` — see the note above.
    firstLoad: data === undefined && loading,
    loading,
    error,
    refetch,
  };
}
