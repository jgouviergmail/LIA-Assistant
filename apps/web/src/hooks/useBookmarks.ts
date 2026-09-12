'use client';

/**
 * The answers a person kept — one page at a time (ADR-282).
 *
 * The gallery hook's shape (`useGeneratedAssets`): the EXACT total behind the
 * page (ADR-185), a `firstLoad` derived from the absence of data rather than
 * from `error` (a refetch clears the error, and a spinner keyed on it
 * unmounts the list mid-refresh), and a page that resets to its start when
 * the search changes and follows the data when the set shrinks.
 */

import { useCallback, useMemo, useState } from 'react';

import { useApiQuery } from '@/hooks/useApiQuery';
import type { BookmarkList } from '@/types/bookmarks';

/** Rows per page — the galleries' rhythm. */
export const BOOKMARKS_PAGE_SIZE = 24;

export interface UseBookmarksReturn {
  items: BookmarkList['items'];
  /** EXACT count over the whole filtered set, not the length of this page. */
  total: number;
  /** How many the account may keep — published because it is enforced. */
  maxPerUser: number;
  page: number;
  totalPages: number;
  setPage: (page: number) => void;
  /** True only before the first payload — never on a refetch. */
  firstLoad: boolean;
  loading: boolean;
  error: Error | null;
  refetch: () => void;
}

/**
 * Build the query string of one page of bookmarks.
 *
 * @param query - The search needle, if any.
 * @param offset - Page start.
 * @returns The path with its query, ready for the API client.
 */
export function bookmarksPath(query: string | undefined, offset: number): string {
  const params = new URLSearchParams({ limit: String(BOOKMARKS_PAGE_SIZE) });
  if (offset > 0) params.set('offset', String(offset));
  const needle = query?.trim();
  if (needle) params.set('q', needle);
  return `/bookmarks?${params.toString()}`;
}

export function useBookmarks(query: string | undefined, enabled: boolean): UseBookmarksReturn {
  const [page, setPage] = useState(1);
  const key = useMemo(() => (query ?? '').trim(), [query]);
  const [lastKey, setLastKey] = useState(key);
  const effectivePage = key === lastKey ? page : 1;
  if (key !== lastKey) {
    // Derived during render rather than in an effect (the hooks ratchet
    // refuses setState in an effect, and an effect would render one frame of
    // the old page against the new search).
    setLastKey(key);
    setPage(1);
  }

  const { data, loading, error, refetch } = useApiQuery<BookmarkList>(
    bookmarksPath(key, (effectivePage - 1) * BOOKMARKS_PAGE_SIZE),
    {
      componentName: 'BookmarkList',
      enabled,
      deps: [key, effectivePage, enabled],
    }
  );

  // The page FOLLOWS the data: deleting the last bookmark of the last page
  // must not leave a blank list under « page 3 of 2 ».
  const totalPages = Math.max(1, Math.ceil((data?.total ?? 0) / BOOKMARKS_PAGE_SIZE));
  const shownPage = Math.min(effectivePage, totalPages);
  if (shownPage !== page) setPage(shownPage);

  return {
    items: data?.items ?? [],
    total: data?.total ?? 0,
    maxPerUser: data?.max_per_user ?? 0,
    page: shownPage,
    totalPages,
    setPage: useCallback((next: number) => setPage(Math.max(1, next)), []),
    firstLoad: data === null || data === undefined,
    loading,
    error,
    refetch,
  };
}
