import { useState, useCallback } from 'react';
import { useApiQuery, UseApiQueryResult } from './useApiQuery';

/**
 * Generic hook for paginated API queries with sorting and search.
 *
 * @template TItem - The type of items in the list
 * @param endpoint - The API endpoint to fetch from
 * @param options - Configuration options
 * @returns Object containing paginated data, pagination controls, and sorting controls
 *
 * @example
 * ```tsx
 * const { items, loading, page, totalPages, goToPage, sortBy, sortOrder, setSort } =
 *   usePaginatedQuery<User>('/users/admin/search', {
 *     componentName: 'UserList',
 *     pageSize: 10,
 *     initialSortBy: 'created_at',
 *     initialSortOrder: 'desc',
 *   });
 * ```
 */
export interface PaginatedResponse<T> {
  /** Array of items for current page */
  items?: T[];
  /** Total number of items across all pages */
  total: number;
  /** Current page number (1-indexed) */
  page: number;
  /** Number of items per page */
  page_size: number;
  /** Total number of pages */
  total_pages: number;
}

export interface UsePaginatedQueryOptions<TSortKey extends string = string> {
  /** Component name for logging */
  componentName: string;
  /** Number of items per page (default: 10) */
  pageSize?: number;
  /** Initial sort field */
  initialSortBy?: TSortKey;
  /** Initial sort order (default: 'asc') */
  initialSortOrder?: 'asc' | 'desc';
  /** Search query */
  searchQuery?: string;
  /** Additional query parameters */
  additionalParams?: Record<string, string | number | boolean>;
  /** Callback on success */
  onSuccess?: (response: PaginatedResponse<unknown>) => void;
  /** Whether to fetch on mount (default: true) */
  enabled?: boolean;
}

export interface UsePaginatedQueryResult<TItem, TSortKey extends string = string>
  extends Omit<UseApiQueryResult<PaginatedResponse<TItem>>, 'data' | 'setData'> {
  /** Array of items for current page */
  items: TItem[];
  /** Total number of items */
  total: number;
  /** Current page number (1-indexed) */
  page: number;
  /** Total number of pages */
  totalPages: number;
  /** Number of items per page */
  pageSize: number;
  /** Current sort field */
  sortBy: TSortKey;
  /** Current sort order */
  sortOrder: 'asc' | 'desc';
  /** Go to specific page */
  goToPage: (page: number) => void;
  /** Go to next page */
  nextPage: () => void;
  /** Go to previous page */
  prevPage: () => void;
  /** Set sort field and order */
  setSort: (sortBy: TSortKey, sortOrder?: 'asc' | 'desc') => void;
  /** Toggle sort order for current field */
  toggleSort: (sortBy: TSortKey) => void;
}

export function usePaginatedQuery<TItem = unknown, TSortKey extends string = string>(
  endpoint: string,
  options: UsePaginatedQueryOptions<TSortKey>
): UsePaginatedQueryResult<TItem, TSortKey> {
  const {
    componentName,
    pageSize = 10,
    initialSortBy,
    initialSortOrder = 'asc',
    searchQuery,
    additionalParams = {},
    onSuccess,
    enabled = true,
  } = options;

  const [page, setPage] = useState(1);
  const [sortBy, setSortBy] = useState<TSortKey | undefined>(initialSortBy);
  const [sortOrder, setSortOrder] = useState<'asc' | 'desc'>(initialSortOrder);

  // Build query params
  const params: Record<string, string | number | boolean> = {
    page,
    page_size: pageSize,
    ...additionalParams,
  };

  if (sortBy) {
    params.sort_by = sortBy;
    params.sort_order = sortOrder;
  }

  if (searchQuery) {
    params.q = searchQuery;
  }

  // Use base API query hook
  const { data, loading, error, refetch } = useApiQuery<PaginatedResponse<TItem>>(endpoint, {
    componentName,
    params,
    enabled,
    onSuccess,
    deps: [page, sortBy, sortOrder, searchQuery],
  });

  // Pagination controls
  const goToPage = useCallback((newPage: number) => {
    setPage(newPage);
  }, []);

  const nextPage = useCallback(() => {
    setPage(prev => Math.min(prev + 1, data?.total_pages || prev));
  }, [data?.total_pages]);

  const prevPage = useCallback(() => {
    setPage(prev => Math.max(prev - 1, 1));
  }, []);

  // Sorting controls
  const setSort = useCallback((newSortBy: TSortKey, newSortOrder: 'asc' | 'desc' = 'asc') => {
    setSortBy(newSortBy);
    setSortOrder(newSortOrder);
    setPage(1); // Reset to first page when sorting changes
  }, []);

  const toggleSort = useCallback(
    (newSortBy: TSortKey) => {
      if (sortBy === newSortBy) {
        // Toggle order if same field
        setSortOrder(prev => (prev === 'asc' ? 'desc' : 'asc'));
      } else {
        // New field, default to ascending
        setSortBy(newSortBy);
        setSortOrder('asc');
      }
      setPage(1); // Reset to first page
    },
    [sortBy]
  );

  return {
    // Data
    items: data?.items || [],
    total: data?.total || 0,
    page: data?.page || page,
    totalPages: data?.total_pages || 1,
    pageSize,

    // States
    loading,
    error,

    // Sorting
    sortBy: sortBy as TSortKey,
    sortOrder,
    setSort,
    toggleSort,

    // Pagination
    goToPage,
    nextPage,
    prevPage,

    // Utility
    refetch,
  };
}
