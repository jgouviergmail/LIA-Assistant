'use client';

/**
 * useRegisterJournal — one reading rhythm for both transparency registers.
 *
 * The action register ("what did LIA do") and the consultation register ("what
 * did it look at") are two distinct lists by decision, never one list with a
 * filter — but they are READ the same way, and two copies of this logic would
 * be two places for the accumulation, the reset and the deduplication to drift.
 *
 * A journal loads more, it does not paginate: pages accumulate keyed by their
 * echoed `offset`, an offset-0 payload RESETS the journal (a refetch is a fresh
 * journal, never a duplicate), and a row arriving twice — the set shifted
 * server-side between two requests — is deduplicated by its row id.
 *
 * `firstLoad` is derived from the ABSENCE of data, never from `error` (the
 * PeerConnectionsSettings defect, 2026-07-31). Page accumulation is adjusted
 * DURING RENDER — the official React pattern for state depending on the latest
 * payload — never in an effect.
 *
 * The `total` is the EXACT number of rows MATCHING the filter, from a
 * server-side aggregate: a count shown to a user is exact or it does not exist,
 * and a global total displayed above a filtered list describes a set the reader
 * cannot see, which is the same defect wearing a different hat.
 */

import { useCallback, useMemo, useState } from 'react';

import { useApiQuery } from '@/hooks/useApiQuery';

/** Rows per request — one number, one reading rhythm for both registers. */
export const REGISTER_PAGE_SIZE = 20;

/** The shape every register page answers with. */
export interface RegisterPage<TEntry> {
  entries: TEntry[];
  /** EXACT number of rows matching the filter, not the page length (ADR-185). */
  total: number;
  limit: number;
  offset: number;
}

export interface UseRegisterJournalResult<TEntry> {
  /** Accumulated entries, newest first. `undefined` before the first payload. */
  entries: TEntry[] | undefined;
  /** Exact total over the FILTERED set, from the latest payload. */
  total: number | undefined;
  /** True when rows exist beyond what is accumulated. */
  hasMore: boolean;
  /** True only before the first payload — never on a refetch. */
  firstLoad: boolean;
  loading: boolean;
  error: Error | null;
  /** Fetch the next page (no-op while loading or when nothing more exists). */
  loadMore: () => void;
  /** Refetch from scratch (offset 0 — the journal resets on arrival). */
  refetch: () => void;
}

/**
 * Read one register, page by page.
 *
 * @param buildPath - Endpoint for a given offset and page size, filters included.
 * @param filterToken - Identifies the CURRENT filter. When it changes the
 *   journal starts over: keeping the accumulated pages would leave rows of the
 *   previous filter on screen, and the first payload of the new one would
 *   arrive at whatever offset the reader had reached.
 * @param componentName - For the query's own diagnostics.
 */
export function useRegisterJournal<TEntry extends { id: string }>(
  buildPath: (offset: number, limit: number) => string,
  filterToken: string,
  componentName: string
): UseRegisterJournalResult<TEntry> {
  const [offset, setOffset] = useState(0);
  const [pages, setPages] = useState<ReadonlyMap<number, TEntry[]>>(new Map());
  const [appliedFilter, setAppliedFilter] = useState(filterToken);

  // Adjusted during render, like the page accumulation below.
  if (appliedFilter !== filterToken) {
    setAppliedFilter(filterToken);
    setOffset(0);
    setPages(new Map());
  }

  const { data, loading, error, refetch } = useApiQuery<RegisterPage<TEntry>>(
    buildPath(offset, REGISTER_PAGE_SIZE),
    { componentName }
  );

  if (data && pages.get(data.offset) !== data.entries) {
    const next = new Map(data.offset === 0 ? [] : pages);
    next.set(data.offset, data.entries);
    setPages(next);
  }

  const entries = useMemo(() => {
    if (pages.size === 0) return undefined;
    const seen = new Set<string>();
    const merged: TEntry[] = [];
    for (const pageOffset of [...pages.keys()].sort((a, b) => a - b)) {
      for (const entry of pages.get(pageOffset) ?? []) {
        if (!seen.has(entry.id)) {
          seen.add(entry.id);
          merged.push(entry);
        }
      }
    }
    return merged;
  }, [pages]);

  const total = data?.total;
  const hasMore = entries !== undefined && total !== undefined && entries.length < total;

  const loadMore = useCallback(() => {
    if (!loading && hasMore) {
      setOffset(current => current + REGISTER_PAGE_SIZE);
    }
  }, [loading, hasMore]);

  const refetchFromScratch = useCallback(() => {
    if (offset === 0) {
      void refetch();
    } else {
      setOffset(0);
    }
  }, [offset, refetch]);

  return {
    entries,
    total,
    hasMore,
    firstLoad: entries === undefined && data === undefined,
    loading,
    error,
    loadMore,
    refetch: refetchFromScratch,
  };
}
