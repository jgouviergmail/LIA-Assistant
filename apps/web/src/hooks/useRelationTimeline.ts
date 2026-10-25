'use client';

/**
 * One relationship's records, newest first, a page at a time (owner request 2026-10-24).
 *
 * Mounted on the section's FIRST opening only — a folded section costs
 * nothing — then page by page through the API's cursor. Keyed on the account
 * AND the person: a page answering an earlier person, or another account, is
 * never shown under the current one, and a late answer is dropped.
 *
 * `revision` is the card's own read of the person: whenever the card reads its
 * records again — a commitment closed or edited from it, a change signalled by
 * the server — the first page is read again, so the timeline never lists what
 * the sections beside it no longer hold. The rows already shown stay until the
 * fresh page replaces them.
 */

import { useCallback, useEffect, useRef, useState } from 'react';

import { useAuth } from '@/hooks/useAuth';
import apiClient from '@/lib/api-client';
import { relationQuerySeparator, relationReadEndpoint } from '@/lib/relations-routing';
import type { RelationTimelineItem, RelationTimelinePage } from '@/lib/relations/timeline';

interface TimelineState {
  key: string;
  items: RelationTimelineItem[];
  next: string | null;
  error: boolean;
  loadingMore: boolean;
  moreFailed: boolean;
}

/** The state a first page leaves: its rows, or the failure to read them. */
async function readFirstPage(endpoint: string, key: string): Promise<TimelineState> {
  const settled = { key, loadingMore: false, moreFailed: false };
  try {
    const page = await apiClient.get<RelationTimelinePage>(endpoint);
    return { ...settled, items: page.items, next: page.next_cursor, error: false };
  } catch {
    return { ...settled, items: [], next: null, error: true };
  }
}

/** What the section reads of the state that answers the current key. */
function viewOf(current: TimelineState | null, enabled: boolean) {
  return {
    items: current?.items ?? [],
    hasMore: (current?.next ?? null) !== null,
    loading: enabled && current === null,
    error: current?.error ?? false,
    loadingMore: current?.loadingMore ?? false,
    moreFailed: current?.moreFailed ?? false,
  };
}

export function useRelationTimeline(name: string | null, revision: unknown) {
  const { user } = useAuth();
  const endpoint = name ? relationReadEndpoint(name, 'timeline') : '';
  const key = endpoint && user?.id ? `${user.id}|${endpoint}` : null;
  const [state, setState] = useState<TimelineState | null>(null);
  const request = useRef(0);

  useEffect(() => {
    if (key === null) return;
    const id = ++request.current;
    void readFirstPage(endpoint, key).then(next => {
      if (id === request.current) setState(next);
    });
  }, [key, endpoint, revision]);

  const current = state?.key === key ? state : null;
  const cursor = current?.next ?? null;
  const busy = current?.loadingMore ?? false;
  const loadMore = useCallback(async () => {
    if (key === null || cursor === null || busy) return;
    const id = request.current;
    setState(previous =>
      previous ? { ...previous, loadingMore: true, moreFailed: false } : previous
    );
    try {
      const page = await apiClient.get<RelationTimelinePage>(
        `${endpoint}${relationQuerySeparator(endpoint)}cursor=${encodeURIComponent(cursor)}`
      );
      if (id !== request.current) return;
      setState(previous =>
        previous && previous.key === key
          ? {
              ...previous,
              items: [...previous.items, ...page.items],
              next: page.next_cursor,
              loadingMore: false,
            }
          : previous
      );
    } catch {
      if (id !== request.current) return;
      setState(previous =>
        previous ? { ...previous, loadingMore: false, moreFailed: true } : previous
      );
    }
  }, [key, endpoint, cursor, busy]);

  return { ...viewOf(current, key !== null), loadMore };
}
