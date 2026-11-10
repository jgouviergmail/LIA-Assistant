'use client';

/** Lazy account-owned pages. Retained rows always keep their own page label. */
import { useCallback, useState } from 'react';
import type { QueryParamValue } from '@/lib/api-client';
import { useAuth } from './useAuth';
import { useApplicationAccountQuery } from './useApplicationAccountQuery';

export const HUB_PAGE_SIZE = 10;

export interface PagedSection<TItem, TPayload = unknown> {
  items: TItem[] | undefined;
  payload: TPayload | undefined;
  total: number;
  page: number;
  setPage: (page: number) => void;
  totalPages: number;
  firstLoad: boolean;
  loading: boolean;
  error: Error | null;
  refetch: () => void;
}

export interface UsePagedSectionOptions<TPayload, TItem> {
  path: string;
  selectItems: (payload: TPayload) => TItem[];
  selectTotal: (payload: TPayload) => number;
  selectAsOf?: (payload: TPayload) => string | undefined;
  /** Validate a wire payload before retaining it or deriving pagination. */
  parse?: (payload: unknown) => TPayload;
  enabled: boolean;
  pageSize?: number;
  /** Client pagination is reserved for a complete collection. */
  pagination?: 'server' | 'client';
  refreshKey?: number;
  /** Criteria identity, including local filters for complete collections. */
  queryKey?: string;
  params?: Record<string, QueryParamValue>;
}

interface PageScope {
  readonly key: string;
}
interface Position {
  scope: PageScope;
  page: number;
  enabled: boolean;
  refreshKey: number | undefined;
}

/** A new owner/filter/closing retires callbacks; a refresh retains its rows. */
function usePagePosition(key: string, enabled: boolean, refreshKey: number | undefined) {
  const [position, setPosition] = useState<Position>(() => ({
    scope: { key },
    page: 1,
    enabled,
    refreshKey,
  }));
  if (position.scope.key !== key || (position.enabled && !enabled)) {
    setPosition({ scope: { key }, page: 1, enabled, refreshKey });
  } else if (position.enabled !== enabled || position.refreshKey !== refreshKey) {
    setPosition({ ...position, page: 1, enabled, refreshKey });
  }
  const scope = position.scope;
  const setPage = useCallback(
    (page: number) => {
      setPosition(current =>
        current.scope !== scope || !current.enabled
          ? current
          : { ...current, page: Math.max(1, page) }
      );
    },
    [scope]
  );
  return { ...position, setPage };
}

function pagedEndpoint(path: string, page: number, size: number): string {
  return `${path}${path.includes('?') ? '&' : '?'}limit=${size}&offset=${(page - 1) * size}`;
}

/** Only an accepted response can move the visible page label. */
function useAcceptedPage<TPayload, TItem>(
  options: UsePagedSectionOptions<TPayload, TItem>,
  scope: PageScope,
  page: number,
  setPage: (page: number) => void,
  pageSize: number
) {
  const { enabled, parse, selectTotal, selectAsOf, pagination = 'server' } = options;
  const [loaded, setLoaded] = useState<{ scope: PageScope; page: number; payload: TPayload }>();
  const accept = useCallback(
    (received: TPayload) => {
      if (!enabled) return;
      const payload = parse ? parse(received) : received;
      const lastPage = Math.max(1, Math.ceil(selectTotal(payload) / pageSize));
      if (pagination === 'server' && page > lastPage) {
        setPage(lastPage);
        return;
      }
      setLoaded({ scope, page, payload });
    },
    [enabled, parse, selectTotal, pageSize, pagination, page, setPage, scope]
  );
  const accepted = loaded?.scope === scope ? loaded : undefined;
  const data = accepted?.payload;
  const asOf = page > 1 && data !== undefined ? selectAsOf?.(data) : undefined;
  return { accept, data, asOf, visiblePage: accepted?.page ?? page };
}

/** Navigation is fenced by the current account/query and retries the requested page. */
function usePageNavigation(
  isCurrent: () => boolean,
  enabled: boolean,
  page: number,
  error: Error | null,
  refetchVerified: () => Promise<unknown>,
  setPage: (page: number) => void,
  pagination: 'server' | 'client'
) {
  const goTo = useCallback(
    (next: number) => {
      if (!isCurrent() || !enabled) return;
      const target = Math.max(1, next);
      if (target === page && error) {
        void refetchVerified();
        return;
      }
      setPage(target);
    },
    [isCurrent, enabled, page, error, refetchVerified, setPage]
  );
  const refetch = useCallback(() => {
    if (!isCurrent() || !enabled) return;
    if (pagination === 'client' || page === 1) void refetchVerified();
    else setPage(1);
  }, [isCurrent, enabled, pagination, page, refetchVerified, setPage]);
  return { goTo, refetch };
}

/** Project only the accepted complete collection; server pages are never sliced twice. */
function pageContents<TPayload, TItem>(
  data: TPayload | undefined,
  options: UsePagedSectionOptions<TPayload, TItem>,
  page: number,
  size: number
) {
  const total = data === undefined ? 0 : options.selectTotal(data);
  const rows = data === undefined ? undefined : options.selectItems(data);
  const items =
    options.pagination === 'client' ? rows?.slice((page - 1) * size, page * size) : rows;
  return { total, totalPages: Math.max(1, Math.ceil(total / size)), items };
}

export function usePagedSection<TPayload, TItem>(
  options: UsePagedSectionOptions<TPayload, TItem>
): PagedSection<TItem, TPayload> {
  const {
    path,
    enabled,
    pageSize = HUB_PAGE_SIZE,
    pagination = 'server',
    refreshKey,
    queryKey,
    params,
  } = options;
  const { user } = useAuth();
  const identity = JSON.stringify([user?.id, path, queryKey, params]);
  const { scope, page, setPage } = usePagePosition(identity, enabled, refreshKey);
  const { accept, data, asOf, visiblePage } = useAcceptedPage(
    options,
    scope,
    page,
    setPage,
    pageSize
  );
  const endpoint = pagination === 'client' ? path : pagedEndpoint(path, page, pageSize);
  const requestParams = asOf === undefined ? params : { ...params, as_of: asOf };
  const { loading, error, refetchVerified, isCurrent } = useApplicationAccountQuery<TPayload>(
    endpoint,
    'usePagedSection',
    enabled,
    accept,
    { params: requestParams, deps: [refreshKey, queryKey] }
  );
  const { total, totalPages, items } = pageContents(data, options, page, pageSize);
  if (enabled && pagination === 'client' && data !== undefined && page > totalPages)
    setPage(totalPages);

  const { goTo, refetch } = usePageNavigation(
    isCurrent,
    enabled,
    page,
    error,
    refetchVerified,
    setPage,
    pagination
  );

  return {
    items,
    payload: data,
    total,
    totalPages,
    page: pagination === 'server' ? visiblePage : page,
    setPage: goTo,
    firstLoad: data === undefined && loading,
    loading,
    error,
    refetch,
  };
}
