'use client';

import { useCallback, useMemo, useState } from 'react';
import { useAuth } from '@/hooks/useAuth';
import { useApplicationAccountQuery } from '@/hooks/useApplicationAccountQuery';
import type {
  ActivityEvent,
  ActivityKindTotal,
  ActivityQuery,
  ActivityTimelineResponse,
} from '@/types/activity';

export const ACTIVITY_PAGE_SIZE = 25;
export const DEFAULT_ACTIVITY_QUERY: ActivityQuery = { q: '', kind: '', sort: 'recent' };

export interface UseActivityTimelineResult {
  events: ActivityEvent[] | undefined;
  totals: ActivityKindTotal[];
  failedKinds: string[];
  windowDays: number | undefined;
  hasMore: boolean;
  firstLoad: boolean;
  loading: boolean;
  error: Error | null;
  loadMore: () => void;
  refetch: () => void;
}

interface Feed {
  key: string;
  generation: { readonly key: string };
  offset: number;
  asOf?: string;
  pages: ReadonlyMap<number, ActivityEvent[]>;
  latest?: ActivityTimelineResponse;
}

function emptyFeed(key: string): Feed {
  return { key, generation: { key }, offset: 0, pages: new Map() };
}

/** A mutable source can shift on deletion; keep each event once across its pages. */
function flattenPages(pages: Feed['pages']): ActivityEvent[] | undefined {
  if (!pages.size) return undefined;
  const events = new Map<string, ActivityEvent>();
  for (const offset of [...pages.keys()].sort((a, b) => a - b)) {
    for (const item of pages.get(offset) ?? []) events.set(`${item.kind}:${item.ref_id}`, item);
  }
  return [...events.values()];
}

/** The account and criteria own every page; only an explicit refresh changes the cut. */
export function useActivityTimeline(criteria = DEFAULT_ACTIVITY_QUERY): UseActivityTimelineResult {
  const { user } = useAuth();
  const key = JSON.stringify([user?.id, criteria.q, criteria.kind, criteria.sort]);
  const [feed, setFeed] = useState(() => emptyFeed(key));
  if (feed.key !== key) setFeed(emptyFeed(key));

  const accept = useCallback(
    (data: ActivityTimelineResponse) => {
      setFeed(current => {
        if (current.key !== key || data.offset !== current.offset) return current;
        if (current.asOf && data.criteria.as_of !== current.asOf) return current;
        const pages = new Map(data.offset === 0 ? [] : current.pages);
        pages.set(data.offset, data.events);
        return { ...current, pages, latest: data };
      });
    },
    [key]
  );

  const { loading, error, isCurrent, refetchVerified } =
    useApplicationAccountQuery<ActivityTimelineResponse>(
      '/activity/timeline',
      'ActivityTimeline',
      true,
      accept,
      {
        params: {
          q: criteria.q,
          kinds: criteria.kind ? [criteria.kind] : [],
          sort: criteria.sort,
          offset: feed.offset,
          limit: ACTIVITY_PAGE_SIZE,
          as_of: feed.asOf,
        },
      }
    );
  const events = useMemo(() => flattenPages(feed.pages), [feed.pages]);
  const latest = feed.latest;
  const generation = feed.generation;
  const hasMore = latest?.has_more ?? false;

  const loadMore = useCallback(() => {
    if (!isCurrent() || loading || !latest?.has_more) return;
    if (latest.offset !== feed.offset) {
      void refetchVerified(); // Retry the failed page, never skip over it.
      return;
    }
    setFeed(current =>
      current.generation !== generation
        ? current
        : {
            ...current,
            offset: latest.offset + latest.limit,
            asOf: latest.criteria.as_of,
          }
    );
  }, [isCurrent, loading, latest, feed.offset, refetchVerified, generation]);

  const refetch = useCallback(() => {
    if (!isCurrent()) return;
    if (feed.offset === 0 && !feed.asOf) void refetchVerified();
    else
      setFeed(current =>
        current.generation !== generation ? current : { ...current, offset: 0, asOf: undefined }
      );
  }, [isCurrent, feed.offset, feed.asOf, refetchVerified, generation]);

  return {
    events,
    totals: latest?.totals ?? [],
    failedKinds: latest?.failed_kinds ?? [],
    windowDays: latest?.window_days,
    hasMore,
    firstLoad: events === undefined,
    loading,
    error,
    loadMore,
    refetch,
  };
}
