'use client';

/**
 * useActivityTimeline — accumulating feed of "what LIA did for you".
 *
 * A chronological feed loads more, it does not paginate: pages accumulate
 * keyed by their echoed `offset`, an offset-0 payload RESETS the feed (a
 * refetch is a fresh feed, never a duplicate), and rows arriving twice
 * across pages — the set shifted server-side between two requests — are
 * deduplicated by (kind, ref_id) so React keys stay unique.
 *
 * `firstLoad` is derived from the ABSENCE of data, never from `error`
 * (the PeerConnectionsSettings defect, 2026-07-31). Page accumulation is
 * adjusted DURING RENDER — the official React pattern for state that
 * depends on the latest payload — never in an effect.
 */

import { useCallback, useMemo, useState } from 'react';

import { useApiQuery } from '@/hooks/useApiQuery';
import type {
  ActivityEvent,
  ActivityKindTotal,
  ActivityTimelineResponse,
} from '@/types/activity';

/** Rows per request — one number, one reading rhythm for the feed. */
export const ACTIVITY_PAGE_SIZE = 25;

export interface UseActivityTimelineResult {
  /** Accumulated feed, newest first. `undefined` before the first payload. */
  events: ActivityEvent[] | undefined;
  /** Exact per-kind totals over the window, from the LATEST payload. */
  totals: ActivityKindTotal[];
  /** Kinds whose source failed — the UI states partial data explicitly. */
  failedKinds: string[];
  /** Look-back window (days) the backend aggregated over. */
  windowDays: number | undefined;
  /** True when rows exist beyond what is accumulated. */
  hasMore: boolean;
  /** True only before the first payload — never on a refetch. */
  firstLoad: boolean;
  loading: boolean;
  error: Error | null;
  /** Fetch the next page (no-op while loading or when nothing more exists). */
  loadMore: () => void;
  /** Refetch from scratch (offset 0 — the feed resets on arrival). */
  refetch: () => void;
}

export function useActivityTimeline(): UseActivityTimelineResult {
  const [offset, setOffset] = useState(0);
  const [pages, setPages] = useState<ReadonlyMap<number, ActivityEvent[]>>(new Map());

  const { data, loading, error, refetch } = useApiQuery<ActivityTimelineResponse>(
    `/activity/timeline?offset=${offset}&limit=${ACTIVITY_PAGE_SIZE}`,
    { componentName: 'useActivityTimeline' }
  );

  // Adjust accumulation during render: an offset-0 payload starts a fresh
  // feed, any other offset adds its page. Reference equality on the events
  // array makes the adjustment idempotent across re-renders.
  if (data && pages.get(data.offset) !== data.events) {
    const next = new Map(data.offset === 0 ? [] : pages);
    next.set(data.offset, data.events);
    setPages(next);
  }

  const events = useMemo(() => {
    if (pages.size === 0) return undefined;
    const seen = new Set<string>();
    const merged: ActivityEvent[] = [];
    for (const pageOffset of [...pages.keys()].sort((a, b) => a - b)) {
      for (const item of pages.get(pageOffset) ?? []) {
        const key = `${item.kind}:${item.ref_id}`;
        if (!seen.has(key)) {
          seen.add(key);
          merged.push(item);
        }
      }
    }
    return merged;
  }, [pages]);

  const hasMore = data?.has_more ?? false;

  const loadMore = useCallback(() => {
    if (!loading && hasMore) {
      setOffset(current => current + ACTIVITY_PAGE_SIZE);
    }
  }, [loading, hasMore]);

  const refetchFromScratch = useCallback(() => {
    if (offset === 0) {
      void refetch();
    } else {
      // Endpoint change triggers the fetch; the offset-0 payload resets.
      setOffset(0);
    }
  }, [offset, refetch]);

  return {
    events,
    totals: data?.totals ?? [],
    failedKinds: data?.failed_kinds ?? [],
    windowDays: data?.window_days,
    hasMore,
    firstLoad: events === undefined && data === undefined,
    loading,
    error,
    loadMore,
    refetch: refetchFromScratch,
  };
}
