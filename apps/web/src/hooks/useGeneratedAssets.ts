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
 * - `firstLoad` covers a pending read without data, never a completed failure:
 *   a refetch clears the error, and a spinner keyed on it unmounts the grid
 *   mid-refresh (`usePagedSection`'s doctrine, measured on
 *   `PeerConnectionsSettings`).
 * - The page resets to its start whenever the family or a filter changes, so
 *   changing a filter never lands on page 4 of a set that now has one page.
 */

import { useCallback, useMemo, useState } from 'react';

import { useAuth } from '@/hooks/useAuth';
import { useApplicationAccountQuery } from '@/hooks/useApplicationAccountQuery';
import { useApplicationResourceSync } from '@/hooks/useApplicationResourceSync';
import type {
  GeneratedAssetFamily,
  GeneratedAssetFilters,
  GeneratedAssetKeepUsage,
  GeneratedAssetList,
} from '@/types/generated-assets';

const releaseGalleryOverride = () => {};

/** Rows per page. One rhythm for the three galleries. */
export const GALLERY_PAGE_SIZE = 24;

export interface UseGeneratedAssetsReturn {
  items: GeneratedAssetList['items'];
  /** EXACT count over the whole filtered set, not the length of this page. */
  total: number;
  /** EXACT bytes behind that count. */
  totalBytes: number;
  /** What the account keeps past the deadline, and its ceilings (ADR-319);
   *  null before the first payload. */
  keep: GeneratedAssetKeepUsage | null;
  page: number;
  totalPages: number;
  setPage: (page: number) => void;
  /** Pending without an owned payload; settled failures expose the error. */
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

/** Owned page metadata and its empty defaults share one projection. */
function galleryValues(data: GeneratedAssetList | undefined): Pick<
  UseGeneratedAssetsReturn,
  'items' | 'total' | 'totalBytes' | 'keep' | 'totalPages'
> {
  const total = data?.total ?? 0;
  return {
    items: data?.items ?? [],
    total,
    totalBytes: data?.total_bytes ?? 0,
    keep: data?.keep ?? null,
    totalPages: Math.max(1, Math.ceil(total / GALLERY_PAGE_SIZE)),
  };
}

export function useGeneratedAssets(
  family: GeneratedAssetFamily,
  filters: GeneratedAssetFilters,
  enabled: boolean
): UseGeneratedAssetsReturn {
  const { user } = useAuth();
  const accountId = user?.id;
  const [page, setPage] = useState(1);
  // The filters are the page's identity: a narrowing that kept the offset
  // would land on a page the new set does not have.
  const key = useMemo(() => JSON.stringify([accountId, family, filters]), [accountId, family, filters]);
  const [lastKey, setLastKey] = useState(key);
  const effectivePage = key === lastKey ? page : 1;
  if (key !== lastKey) {
    // Derived during render rather than in an effect: the react-hooks ratchet
    // refuses setState in an effect, and an effect would render one frame of
    // the OLD page against the NEW filters.
    setLastKey(key);
    setPage(1);
  }

  const { data, loading, error, refetch, ownerId } = useApplicationAccountQuery<GeneratedAssetList>(
    galleryPath(family, filters, (effectivePage - 1) * GALLERY_PAGE_SIZE),
    'GeneratedAssetsSettings',
    enabled
  );
  useApplicationResourceSync(ownerId, 'generated_assets', refetch, releaseGalleryOverride);

  // The page FOLLOWS the data. Deleting the last file of the last page used to
  // leave a blank grid under a pager reading « page 3 of 2 »: the set shrank
  // and the page stayed where it was. Clamped on render rather than in an
  // effect, for the same reason the filter reset is (one frame of the old page
  // against the new set, and the hooks ratchet refuses setState in an effect).
  const values = galleryValues(data);
  const shownPage = Math.min(effectivePage, values.totalPages);
  if (shownPage !== page) setPage(shownPage);

  return {
    ...values,
    page: shownPage,
    setPage: useCallback((next: number) => setPage(Math.max(1, next)), []),
    firstLoad: loading && data == null,
    loading,
    error,
    refetch,
  };
}
