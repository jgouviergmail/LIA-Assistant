/** Exercise pagination through the actual account/query lifecycle. */
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { renderHook, act, waitFor } from '@testing-library/react';
import type { RequestConfig } from '@/lib/api-client';
import type { ActivityEvent, ActivityTimelineResponse } from '@/types/activity';

const { get, useAuth } = vi.hoisted(() => ({ get: vi.fn(), useAuth: vi.fn() }));
vi.mock('@/hooks/useAuth', () => ({ useAuth }));
vi.mock('@/lib/api-client', async importOriginal => ({
  ...(await importOriginal<typeof import('@/lib/api-client')>()),
  default: { get },
}));
import { useActivityTimeline, ACTIVITY_PAGE_SIZE } from '../useActivityTimeline';

const cut = '2026-11-01T12:00:00Z';
function event(refId: string): ActivityEvent {
  return { kind: 'habit_detected', ref_id: refId, occurred_at: cut, text: refId, status: null };
}
function payload(over: Partial<ActivityTimelineResponse> = {}): ActivityTimelineResponse {
  return {
    events: [event('a')],
    totals: [{ kind: 'habit_detected', total: 30, truncated: false }],
    has_more: true,
    offset: 0,
    limit: ACTIVITY_PAGE_SIZE,
    window_days: 30,
    failed_kinds: [],
    criteria: { q: '', kinds: [], sort: 'recent', as_of: cut },
    ...over,
  };
}
beforeEach(() => {
  vi.resetAllMocks();
  useAuth.mockReturnValue({ user: { id: 'one' } });
  get.mockResolvedValue(payload());
});

describe('activity feed', () => {
  it('rejects a retained paging callback even after returning to the same filter', async () => {
    const { result, rerender } = renderHook(
      ({ q }) => useActivityTimeline({ q, kind: '', sort: 'recent' }),
      { initialProps: { q: 'first' } }
    );
    await waitFor(() => expect(result.current.events).toHaveLength(1));
    const retired = result.current.loadMore;
    rerender({ q: 'second' });
    await waitFor(() => expect(get).toHaveBeenCalledTimes(2));
    let finish: (value: ActivityTimelineResponse) => void = () => {};
    get.mockReturnValueOnce(
      new Promise<ActivityTimelineResponse>(resolve => {
        finish = resolve;
      })
    );
    rerender({ q: 'first' });
    await waitFor(() => expect(get).toHaveBeenCalledTimes(3));
    act(retired);
    await act(async () => {
      finish(payload());
    });
    expect(get).toHaveBeenCalledTimes(3);
  });
  it('loads first, appends with the server cut, deduplicates and refreshes from zero', async () => {
    const { result } = renderHook(() => useActivityTimeline());
    expect(result.current.firstLoad).toBe(true);
    await waitFor(() => expect(result.current.events).toHaveLength(1));
    get.mockResolvedValueOnce(
      payload({ offset: ACTIVITY_PAGE_SIZE, events: [event('a'), event('b')], has_more: false })
    );
    act(() => result.current.loadMore());
    await waitFor(() => expect(result.current.events).toHaveLength(2));
    expect(get).toHaveBeenLastCalledWith(
      '/activity/timeline',
      expect.objectContaining({
        params: expect.objectContaining({ offset: ACTIVITY_PAGE_SIZE, as_of: cut }),
      })
    );
    expect(result.current.hasMore).toBe(false);
    get.mockResolvedValueOnce(payload({ events: [event('z')] }));
    act(() => result.current.refetch());
    expect(result.current.events).toHaveLength(2);
    await waitFor(() => expect(result.current.events?.map(item => item.ref_id)).toEqual(['z']));
    expect(get).toHaveBeenLastCalledWith(
      '/activity/timeline',
      expect.objectContaining({
        params: expect.objectContaining({ offset: 0, as_of: undefined }),
      })
    );
  });

  it('retires the prior filter and its in-flight page without mixing results', async () => {
    const { result, rerender } = renderHook(
      ({ q }) => useActivityTimeline({ q, sort: 'oldest', kind: 'habit_detected' }),
      { initialProps: { q: '' } }
    );
    await waitFor(() => expect(result.current.events).toHaveLength(1));
    let finish: (value: ActivityTimelineResponse) => void = () => {};
    get.mockReturnValueOnce(
      new Promise<ActivityTimelineResponse>(resolve => {
        finish = resolve;
      })
    );
    act(() => result.current.loadMore());
    await waitFor(() => expect(get).toHaveBeenCalledTimes(2));
    get.mockResolvedValueOnce(payload({ events: [], has_more: false }));
    rerender({ q: 'none' });
    expect(result.current.events).toBeUndefined();
    await waitFor(() => expect(result.current.events).toEqual([]));
    await act(async () => {
      finish(payload({ offset: ACTIVITY_PAGE_SIZE, events: [event('stale')] }));
    });
    expect(result.current.events).toEqual([]);
    expect(get).toHaveBeenLastCalledWith(
      '/activity/timeline',
      expect.objectContaining({
        params: expect.objectContaining({
          q: 'none',
          sort: 'oldest',
          kinds: ['habit_detected'],
          offset: 0,
        }),
      })
    );
  });

  it('hides the previous owner immediately and rejects its retained callbacks', async () => {
    const { result, rerender } = renderHook(() => useActivityTimeline());
    await waitFor(() => expect(result.current.events).toHaveLength(1));
    const retired = { loadMore: result.current.loadMore, refetch: result.current.refetch };
    let finish: (value: ActivityTimelineResponse) => void = () => {};
    get.mockReturnValueOnce(
      new Promise<ActivityTimelineResponse>(resolve => {
        finish = resolve;
      })
    );
    useAuth.mockReturnValue({ user: { id: 'two' } });
    rerender();
    expect(result.current.events).toBeUndefined();
    act(() => {
      retired.loadMore();
      retired.refetch();
    });
    await waitFor(() => expect(get).toHaveBeenCalledTimes(2));
    expect(get).toHaveBeenLastCalledWith(
      '/activity/timeline',
      expect.objectContaining({ params: expect.objectContaining({ offset: 0 }) })
    );
    await act(async () => {
      finish(payload({ events: [event('owner-two')] }));
    });
    expect(result.current.events?.[0].ref_id).toBe('owner-two');
  });

  it('keeps existing rows on failed refresh and retries the failed page without advancing', async () => {
    const { result } = renderHook(() => useActivityTimeline());
    await waitFor(() => expect(result.current.events).toHaveLength(1));
    get.mockRejectedValueOnce(new Error('offline'));
    act(() => result.current.refetch());
    await waitFor(() => expect(result.current.error).toBeInstanceOf(Error));
    expect(result.current.events?.[0].ref_id).toBe('a');
    const refreshed = Promise.withResolvers<ActivityTimelineResponse>();
    get.mockReturnValueOnce(refreshed.promise);
    act(() => result.current.refetch());
    // Starting a retry clears its error before the replacement page arrives.
    expect(result.current.error).toBeNull();
    expect(result.current.loading).toBe(true);
    expect(result.current.events?.[0].ref_id).toBe('a');
    expect(result.current.failedKinds).toEqual([]);
    await act(async () => {
      refreshed.resolve(payload({ failed_kinds: ['interest_notification'] }));
    });
    await waitFor(() => expect(result.current.failedKinds).toEqual(['interest_notification']));
    expect(result.current.error).toBeNull();
    expect(result.current.loading).toBe(false);
    get.mockRejectedValueOnce(new Error('offline'));
    act(() => result.current.loadMore());
    await waitFor(() => expect(result.current.error).toBeInstanceOf(Error));
    get.mockResolvedValueOnce(
      payload({ offset: ACTIVITY_PAGE_SIZE, events: [event('b')], has_more: false })
    );
    act(() => result.current.loadMore());
    await waitFor(() => expect(result.current.events).toHaveLength(2));
    const last: RequestConfig | undefined = get.mock.lastCall?.[1];
    expect(last?.params?.offset).toBe(ACTIVITY_PAGE_SIZE);
  });
});
