/**
 * useActivityTimeline — the accumulation contract of the activity feed.
 *
 * A chronological feed loads more, it does not paginate: pages accumulate,
 * a payload at offset 0 RESETS the feed (a refetch is a fresh feed, not a
 * duplicate), and rows arriving twice across pages (the set shifted between
 * requests) are deduplicated by (kind, ref_id) so React keys stay unique.
 * `firstLoad` is keyed on the ABSENCE of data, never on `error`.
 */

import { describe, it, expect, vi, beforeEach } from 'vitest';
import { renderHook, act } from '@testing-library/react';

const { useApiQuery } = vi.hoisted(() => ({ useApiQuery: vi.fn() }));
vi.mock('@/hooks/useApiQuery', () => ({ useApiQuery }));

import {
  useActivityTimeline,
  ACTIVITY_PAGE_SIZE,
} from '../useActivityTimeline';
import type { ActivityEvent, ActivityTimelineResponse } from '@/types/activity';

function event(refId: string, kind = 'habit_detected'): ActivityEvent {
  return {
    kind,
    ref_id: refId,
    occurred_at: '2026-08-19T10:00:00Z',
    text: `event ${refId}`,
    status: null,
  };
}

function payload(over: Partial<ActivityTimelineResponse> = {}): ActivityTimelineResponse {
  return {
    events: [],
    totals: [],
    has_more: false,
    offset: 0,
    limit: ACTIVITY_PAGE_SIZE,
    window_days: 30,
    failed_kinds: [],
    ...over,
  };
}

function answer(data: ActivityTimelineResponse | undefined, over: Record<string, unknown> = {}) {
  useApiQuery.mockReturnValue({
    data,
    loading: data === undefined,
    error: null,
    refetch: vi.fn(),
    ...over,
  });
}

beforeEach(() => {
  useApiQuery.mockReset();
});

describe('useActivityTimeline', () => {
  it('requests the first page and reports firstLoad while empty-handed', () => {
    answer(undefined);

    const { result } = renderHook(() => useActivityTimeline());

    expect(useApiQuery).toHaveBeenCalledWith(
      `/activity/timeline?offset=0&limit=${ACTIVITY_PAGE_SIZE}`,
      expect.objectContaining({ componentName: 'useActivityTimeline' })
    );
    expect(result.current.firstLoad).toBe(true);
    expect(result.current.events).toBeUndefined();
  });

  it('exposes the first page with its totals and window', () => {
    answer(
      payload({
        events: [event('a'), event('b')],
        totals: [{ kind: 'habit_detected', total: 2, truncated: false }],
        has_more: true,
        window_days: 30,
      })
    );

    const { result } = renderHook(() => useActivityTimeline());

    expect(result.current.events?.map(e => e.ref_id)).toEqual(['a', 'b']);
    expect(result.current.totals).toEqual([
      { kind: 'habit_detected', total: 2, truncated: false },
    ]);
    expect(result.current.hasMore).toBe(true);
    expect(result.current.windowDays).toBe(30);
    expect(result.current.firstLoad).toBe(false);
  });

  it('loadMore appends the next page after the current one', () => {
    answer(payload({ events: [event('a')], has_more: true }));
    const { result, rerender } = renderHook(() => useActivityTimeline());

    act(() => result.current.loadMore());
    answer(
      payload({ events: [event('b')], offset: ACTIVITY_PAGE_SIZE, has_more: false })
    );
    rerender();

    expect(useApiQuery).toHaveBeenLastCalledWith(
      `/activity/timeline?offset=${ACTIVITY_PAGE_SIZE}&limit=${ACTIVITY_PAGE_SIZE}`,
      expect.anything()
    );
    expect(result.current.events?.map(e => e.ref_id)).toEqual(['a', 'b']);
    expect(result.current.hasMore).toBe(false);
  });

  it('deduplicates rows that arrive twice across pages', () => {
    answer(payload({ events: [event('a'), event('b')], has_more: true }));
    const { result, rerender } = renderHook(() => useActivityTimeline());

    act(() => result.current.loadMore());
    // The set shifted server-side: "b" comes back on page 2.
    answer(
      payload({ events: [event('b'), event('c')], offset: ACTIVITY_PAGE_SIZE })
    );
    rerender();

    expect(result.current.events?.map(e => e.ref_id)).toEqual(['a', 'b', 'c']);
  });

  it('a payload at offset 0 resets the feed instead of appending', () => {
    answer(payload({ events: [event('a')], has_more: true }));
    const { result, rerender } = renderHook(() => useActivityTimeline());

    act(() => result.current.loadMore());
    answer(payload({ events: [event('b')], offset: ACTIVITY_PAGE_SIZE }));
    rerender();
    expect(result.current.events).toHaveLength(2);

    // Fresh feed (e.g. after refetch): offset-0 payload replaces everything.
    answer(payload({ events: [event('z')] }));
    rerender();

    expect(result.current.events?.map(e => e.ref_id)).toEqual(['z']);
  });

  it('loadMore is a no-op while nothing more exists', () => {
    answer(payload({ events: [event('a')], has_more: false }));
    const { result, rerender } = renderHook(() => useActivityTimeline());

    act(() => result.current.loadMore());
    rerender();

    expect(useApiQuery).toHaveBeenLastCalledWith(
      `/activity/timeline?offset=0&limit=${ACTIVITY_PAGE_SIZE}`,
      expect.anything()
    );
  });

  it('surfaces failed kinds so the UI can state partial data', () => {
    answer(payload({ events: [event('a')], failed_kinds: ['interest_notification'] }));

    const { result } = renderHook(() => useActivityTimeline());

    expect(result.current.failedKinds).toEqual(['interest_notification']);
  });
});
