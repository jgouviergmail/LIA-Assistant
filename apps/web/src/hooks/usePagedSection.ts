'use client';

/** Independent lazy pages with exact counts, retained refresh data and a
 * first-load state derived from absence of data. Closing resets the position.
 * Complete, unpaged endpoints explicitly opt into local pagination. */

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
  /** Endpoint without paging parameters; client pagination keeps it unchanged. */
  path: string;
  /** Pull the rows out of the payload. */
  selectItems: (payload: TPayload) => TItem[];
  /** Pull the exact total out of the payload. */
  selectTotal: (payload: TPayload) => number;
  /** Fetch only while the section is open: a folded list costs nothing. */
  enabled: boolean;
  pageSize?: number;
  /**
   * Server pages by default. Use client only for an endpoint returning its
   * complete collection, such as scheduled actions, which accepts no offset.
   */
  pagination?: 'server' | 'client';
  /**
   * Bump it when a write elsewhere changed the set (a broadcast was just sent):
   * the section refetches FROM ITS FIRST PAGE and keeps what it shows meanwhile
   * — a refresh, never a first load. Omitted, nothing ever forces a refetch.
   */
  refreshKey?: number;
}

/** Requested position and the two explicit transitions that reset it. */
function usePagePosition(enabled: boolean, refreshKey: number | undefined) {
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
  // A new refresh key means the set changed under the reader: back to its
  // start, where the change is (same render-phase adjustment as above).
  const [lastRefreshKey, setLastRefreshKey] = useState(refreshKey);
  if (lastRefreshKey !== refreshKey) {
    setLastRefreshKey(refreshKey);
    setPage(1);
  }

  return {
    page,
    setPage,
    canRecoverPage: enabled && wasEnabled === enabled && lastRefreshKey === refreshKey,
  };
}

interface LoadedPageOptions<TPayload> {
  data: TPayload | undefined;
  loading: boolean;
  error: Error | null;
  page: number;
  totalPages: number;
  canRecoverPage: boolean;
  setPage: (page: number) => void;
}

/** Keep the page belonging to retained rows, independently of the next request. */
function useLoadedPage<TPayload>({
  data,
  loading,
  error,
  page,
  totalPages,
  canRecoverPage,
  setPage,
}: LoadedPageOptions<TPayload>): number {
  const [loaded, setLoaded] = useState(() => ({ data, page }));
  // A new endpoint first exposes the previous data. It is not a successful
  // response for that endpoint, and must never invalidate its requested page.
  if (data === undefined || loading || error || data === loaded.data) return loaded.page;

  setLoaded({ data, page });
  if (canRecoverPage && page > totalPages) setPage(totalPages);
  return page;
}

/** An error must label retained server rows with the page they came from. */
function retainLoadedPage<TPayload>(
  {
    data,
    error,
    canRecoverPage,
  }: Pick<LoadedPageOptions<TPayload>, 'data' | 'error' | 'canRecoverPage'>,
  pagination: 'server' | 'client'
): boolean {
  return pagination === 'server' && error !== null && canRecoverPage && data !== undefined;
}

function pagedEndpoint(path: string, page: number, pageSize: number): string {
  const separator = path.includes('?') ? '&' : '?';
  return `${path}${separator}limit=${pageSize}&offset=${(page - 1) * pageSize}`;
}

export function usePagedSection<TPayload, TItem>({
  path,
  selectItems,
  selectTotal,
  enabled,
  pageSize = HUB_PAGE_SIZE,
  pagination = 'server',
  refreshKey,
}: UsePagedSectionOptions<TPayload, TItem>): PagedSection<TItem> {
  const { page, setPage, canRecoverPage } = usePagePosition(enabled, refreshKey);
  const endpoint = pagination === 'client' ? path : pagedEndpoint(path, page, pageSize);
  const { data, loading, error, refetch } = useApiQuery<TPayload>(endpoint, {
    componentName: 'usePagedSection',
    enabled,
    deps: [refreshKey],
  });

  const total = data === undefined ? 0 : selectTotal(data);
  const totalPages = Math.max(1, Math.ceil(total / pageSize));
  const loadedPage = useLoadedPage({
    data,
    loading,
    error,
    page,
    totalPages,
    canRecoverPage,
    setPage,
  });
  // A complete client collection is authoritative for every local page.
  if (canRecoverPage && pagination === 'client' && data !== undefined && page > totalPages) {
    setPage(totalPages);
  }

  const rows = data === undefined ? undefined : selectItems(data);
  const items =
    pagination === 'client' ? rows?.slice((page - 1) * pageSize, page * pageSize) : rows;
  // On failure the retained server rows still belong to their loaded page.
  // Keep the request position internally, so retry can target the failed page.
  const visiblePage = retainLoadedPage({ data, error, canRecoverPage }, pagination)
    ? loadedPage
    : page;
  const goTo = useCallback(
    (next: number) => {
      const nextPage = Math.max(1, next);
      if (nextPage === page && error) {
        void refetch();
        return;
      }
      setPage(nextPage);
    },
    [page, error, refetch, setPage]
  );

  return {
    items,
    total,
    page: visiblePage,
    setPage: goTo,
    totalPages,
    // Derived from `data`, never from `error` — see the note above.
    firstLoad: data === undefined && loading,
    loading,
    error,
    refetch,
  };
}
