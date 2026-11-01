'use client';

/**
 * One cursor-paged listing of the « Tools » section (ADR-369).
 *
 * Shaped after `useNeedlePage`: loading is DERIVED from the key (the account,
 * the path, the params), so no frame shows the previous listing as the answer
 * to new params, a late answer to old params is dropped, and a change of
 * account clears the list at once. Every workbench listing answers one page
 * and the token of the next (`{ items, next_page_token }`; a mail listing adds
 * the hits it could not read, `skipped`, summed over the pages); `loadMore`
 * appends it until the token is null.
 *
 * A refresh re-reads page one IN PLACE: what is on screen stays until its
 * answer lands, and a failed refresh withdraws it (owner rule 2026-10-21). A
 * page asked for during a refresh is not appended to the listing that is about
 * to replace it. `replaceItem` applies an optimistic or confirmed change to one
 * row — `null` removes it — without a read.
 */
import { useCallback, useEffect, useRef, useState } from 'react';

import { useAuth } from '@/hooks/useAuth';
import apiClient, { type QueryParamValue } from '@/lib/api-client';
import { paramsOf, serialiseParams } from '@/lib/workbench/params';

/** What a workbench listing answers. */
export interface WorkbenchPage<T> {
  items: T[];
  next_page_token: string | null;
  /** Hits the provider listed but could not read (a mail listing): the page is partial. */
  skipped?: number;
  /** A page answered in one go (a search, a group) that may hold more. */
  truncated?: boolean;
}

export interface WorkbenchPageState<T> {
  items: T[];
  /** The next page's token; null on the last page. */
  nextToken: string | null;
  /** The first page of the current key is not read yet. */
  loading: boolean;
  /** A next page is being read. */
  loadingMore: boolean;
  /** What the pages read could not show, summed (ADR-185: a cut is stated). */
  skipped: number;
  /** A page read says it may hold more than it showed (a search, a group). */
  truncated: boolean;
  /** Why the last read failed (`workbenchRefusal` tells it), else null. */
  error: unknown;
  loadMore: () => Promise<void>;
  refresh: () => Promise<void>;
  replaceItem: (id: string, next: T | null) => void;
}

interface Listing<T> {
  key: string;
  items: T[];
  nextToken: string | null;
  skipped: number;
  truncated: boolean;
  error: unknown;
}

/** A listing whose first page just landed. */
function firstPage<T>(key: string, answer: WorkbenchPage<T>): Listing<T> {
  return {
    key,
    items: answer.items,
    nextToken: answer.next_page_token,
    skipped: answer.skipped ?? 0,
    truncated: answer.truncated ?? false,
    error: null,
  };
}

/** A listing whose first read failed: nothing shown, the reason kept. */
function failed<T>(key: string, error: unknown): Listing<T> {
  return { key, items: [], nextToken: null, skipped: 0, truncated: false, error };
}

/**
 * @param path - The listing's endpoint; null reads nothing.
 * @param params - Its params (a folder, a filter); part of the key.
 * @returns The listing's state and its three gestures.
 */
export function useWorkbenchPage<T extends { id: string }>(
  path: string | null,
  params: Readonly<Record<string, QueryParamValue>>
): WorkbenchPageState<T> {
  const { user } = useAuth();
  const owner = user?.id;
  const queryKey = serialiseParams(params);
  const key = owner && path ? `${owner}|${path}|${queryKey}` : null;
  const [listing, setListing] = useState<Listing<T> | null>(null);
  const [moreFor, setMoreFor] = useState<string | null>(null);
  // Every first read and refresh starts a new listing; an answer to an older
  // one is dropped. A refresh in flight refuses a next page.
  const generation = useRef(0);
  const refreshing = useRef(false);
  // The key whose next page is being read, set synchronously: two « more »
  // asked before a render must not both read (and append) the same page.
  const moreInFlight = useRef<string | null>(null);

  useEffect(() => {
    if (key === null || path === null) return;
    const listingId = ++generation.current;
    refreshing.current = false;
    const transport = new AbortController();
    apiClient
      .get<WorkbenchPage<T>>(path, { params: paramsOf(queryKey), signal: transport.signal })
      .then(answer => {
        if (listingId !== generation.current) return;
        setListing(firstPage(key, answer));
      })
      .catch((error: unknown) => {
        if (listingId !== generation.current || transport.signal.aborted) return;
        setListing(failed(key, error));
      });
    return () => transport.abort();
  }, [key, path, queryKey]);

  const refresh = useCallback(async () => {
    if (key === null || path === null) return;
    const listingId = ++generation.current;
    refreshing.current = true;
    try {
      const answer = await apiClient.get<WorkbenchPage<T>>(path, { params: paramsOf(queryKey) });
      if (listingId === generation.current) setListing(firstPage(key, answer));
    } catch (error: unknown) {
      if (listingId === generation.current) setListing(failed(key, error));
    } finally {
      if (listingId === generation.current) refreshing.current = false;
    }
  }, [key, path, queryKey]);

  const current = listing !== null && listing.key === key;
  const nextToken = current ? listing.nextToken : null;

  const loadMore = useCallback(async () => {
    if (key === null || path === null || !nextToken || refreshing.current) return;
    if (moreInFlight.current === key) return;
    moreInFlight.current = key;
    const listingId = generation.current;
    setMoreFor(key);
    try {
      const answer = await apiClient.get<WorkbenchPage<T>>(path, {
        params: { ...paramsOf(queryKey), page_token: nextToken },
      });
      if (listingId !== generation.current) return;
      setListing(previous =>
        previous && previous.key === key
          ? {
              key,
              items: [...previous.items, ...answer.items],
              nextToken: answer.next_page_token,
              skipped: previous.skipped + (answer.skipped ?? 0),
              truncated: previous.truncated || (answer.truncated ?? false),
              error: null,
            }
          : previous
      );
    } catch (error: unknown) {
      if (listingId !== generation.current) return;
      // The page on screen stays; the token stays too, so « more » can be asked again.
      setListing(previous =>
        previous && previous.key === key ? { ...previous, error } : previous
      );
    } finally {
      if (moreInFlight.current === key) moreInFlight.current = null;
      setMoreFor(asked => (asked === key ? null : asked));
    }
  }, [key, path, queryKey, nextToken]);

  const replaceItem = useCallback(
    (id: string, next: T | null) => {
      setListing(previous => {
        if (!previous || previous.key !== key) return previous;
        const items =
          next === null
            ? previous.items.filter(item => item.id !== id)
            : previous.items.map(item => (item.id === id ? next : item));
        return { ...previous, items };
      });
    },
    [key]
  );

  return {
    items: current ? listing.items : [],
    nextToken,
    loading: key !== null && !current,
    loadingMore: moreFor !== null && moreFor === key,
    skipped: current ? listing.skipped : 0,
    truncated: current ? listing.truncated : false,
    error: current ? listing.error : null,
    loadMore,
    refresh,
    replaceItem,
  };
}
