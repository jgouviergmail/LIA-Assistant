'use client';

/**
 * The gallery of what LIA produced (ADR-279).
 *
 * One family at a time — images, documents, browser screenshots — with the
 * EXACT total behind the page (ADR-185) and the bytes it holds, so the section
 * can state how much space a person is carrying rather than counting the rows
 * it happens to show.
 *
 * Two rules the hook obeys, both learned elsewhere in this app:
 *
 * - `firstLoad` is derived from the ABSENCE of data, never from `error`: a
 *   refetch clears the error, and a spinner keyed on it unmounts the grid
 *   mid-refresh (`usePagedSection`'s doctrine, measured on
 *   `PeerConnectionsSettings`).
 * - The page resets to its start whenever the family or a filter changes, so
 *   changing a filter never lands on page 4 of a set that now has one page.
 */

import { useCallback, useMemo, useState } from 'react';

import { useApiQuery } from '@/hooks/useApiQuery';
import type { GeneratedAssetFamily, GeneratedAssetFilters, GeneratedAssetList } from '@/types/generated-assets';

/** Rows per page. One rhythm for the three galleries. */
export const GALLERY_PAGE_SIZE = 24;

export interface UseGeneratedAssetsReturn {
  items: GeneratedAssetList['items'];
  /** EXACT count over the whole filtered set, not the length of this page. */
  total: number;
  /** EXACT bytes behind that count. */
  totalBytes: number;
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
 * Build the query string of one gallery page.
 *
 * @param family - Which gallery.
 * @param filters - What it is narrowed to.
 * @param offset - Page start.
 * @returns The path with its query, ready for the API client.
 */
export function galleryPath(
  family: GeneratedAssetFamily,
  filters: GeneratedAssetFilters,
  offset: number
): string {
  const params = new URLSearchParams({ family, limit: String(GALLERY_PAGE_SIZE) });
  if (offset > 0) params.set('offset', String(offset));
  // An unset filter costs no parameter: the server keeps its own default, and
  // a blank `q=` would narrow nothing while looking like a search.
  const needle = filters.q?.trim();
  if (needle) params.set('q', needle);
  if (filters.createdAfter) params.set('created_after', filters.createdAfter);
  if (filters.createdBefore) params.set('created_before', filters.createdBefore);
  if (filters.expiresBefore) params.set('expires_before', filters.expiresBefore);
  if (filters.sort && filters.sort !== 'created_desc') params.set('sort', filters.sort);
  return `/generated-assets?${params.toString()}`;
}

export function useGeneratedAssets(
  family: GeneratedAssetFamily,
  filters: GeneratedAssetFilters,
  enabled: boolean
): UseGeneratedAssetsReturn {
  const [page, setPage] = useState(1);
  // The filters are the page's identity: a narrowing that kept the offset
  // would land on a page the new set does not have.
  const key = useMemo(() => JSON.stringify([family, filters]), [family, filters]);
  const [lastKey, setLastKey] = useState(key);
  const effectivePage = key === lastKey ? page : 1;
  if (key !== lastKey) {
    // Derived during render rather than in an effect: the react-hooks ratchet
    // refuses setState in an effect, and an effect would render one frame of
    // the OLD page against the NEW filters.
    setLastKey(key);
    setPage(1);
  }

  const { data, loading, error, refetch } = useApiQuery<GeneratedAssetList>(
    galleryPath(family, filters, (effectivePage - 1) * GALLERY_PAGE_SIZE),
    {
      componentName: 'GeneratedAssetsSettings',
      enabled,
      deps: [key, effectivePage, enabled],
    }
  );

  // The page FOLLOWS the data. Deleting the last file of the last page used to
  // leave a blank grid under a pager reading « page 3 of 2 »: the set shrank
  // and the page stayed where it was. Clamped on render rather than in an
  // effect, for the same reason the filter reset is (one frame of the old page
  // against the new set, and the hooks ratchet refuses setState in an effect).
  const totalPages = Math.max(1, Math.ceil((data?.total ?? 0) / GALLERY_PAGE_SIZE));
  const shownPage = Math.min(effectivePage, totalPages);
  if (shownPage !== page) setPage(shownPage);

  return {
    items: data?.items ?? [],
    total: data?.total ?? 0,
    totalBytes: data?.total_bytes ?? 0,
    page: shownPage,
    totalPages,
    setPage: useCallback((next: number) => setPage(Math.max(1, next)), []),
    firstLoad: data === null || data === undefined,
    loading,
    error,
    refetch,
  };
}
