/** Real query/account lifetimes, including lazy reads and late page responses. */
import { act, renderHook, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import type { UsePagedSectionOptions } from '../usePagedSection';

const { get, useAuth } = vi.hoisted(() => ({ get: vi.fn(), useAuth: vi.fn() }));
vi.mock('@/hooks/useAuth', () => ({ useAuth }));
vi.mock('@/lib/api-client', async importOriginal => ({
  ...(await importOriginal<typeof import('@/lib/api-client')>()),
  default: { get },
}));
import { usePagedSection } from '../usePagedSection';

interface Payload {
  rows: string[];
  total: number;
  as_of?: string;
}
function payload(rows = ['first'], total = 35): Payload {
  return { rows, total };
}
function options(
  over: Partial<UsePagedSectionOptions<Payload, string>> = {}
): UsePagedSectionOptions<Payload, string> {
  return {
    path: '/things',
    enabled: true,
    selectItems: p => p.rows,
    selectTotal: p => p.total,
    ...over,
  };
}
function delayed() {
  let resolve: (value: Payload) => void = () => {};
  const promise = new Promise<Payload>(done => {
    resolve = done;
  });
  return { promise, resolve };
}
beforeEach(() => {
  vi.resetAllMocks();
  useAuth.mockReturnValue({ user: { id: 'one' } });
  get.mockResolvedValue(payload());
});

describe('owned section pages', () => {
  it('carries the accepted server cut to later pages and renews it on refresh', async () => {
    const cut = '2026-11-01T10:00:00Z';
    get.mockResolvedValueOnce({ ...payload(), as_of: cut });
    const { result } = renderHook(() => usePagedSection(options({ selectAsOf: p => p.as_of })));
    await waitFor(() => expect(result.current.items).toEqual(['first']));
    get.mockResolvedValueOnce({ ...payload(['second']), as_of: cut });
    act(() => result.current.setPage(2));
    await waitFor(() => expect(result.current.items).toEqual(['second']));
    expect(get.mock.lastCall?.[1].params).toEqual({ as_of: cut });
    act(() => result.current.refetch());
    await waitFor(() => expect(get).toHaveBeenCalledTimes(3));
    expect(get.mock.lastCall?.[1].params).toBeUndefined();
  });

  it('refuses malformed pages without replacing the last accepted rows', async () => {
    const parse = (value: unknown): Payload => {
      if (value === null) throw new Error('Malformed page');
      return payload(['valid']);
    };
    const { result } = renderHook(() => usePagedSection(options({ parse })));
    await waitFor(() => expect(result.current.items).toEqual(['valid']));
    get.mockResolvedValueOnce(null);
    act(() => result.current.refetch());
    await waitFor(() => expect(result.current.error).not.toBeNull());
    expect(result.current.items).toEqual(['valid']);
  });
  it('retires old filters before reading the new first page, even with a late page four', async () => {
    const { result, rerender } = renderHook(
      ({ q }) => usePagedSection(options({ queryKey: q, params: { q } })),
      { initialProps: { q: 'old' } }
    );
    await waitFor(() => expect(result.current.items).toEqual(['first']));
    const late = delayed();
    get.mockReturnValueOnce(late.promise);
    act(() => result.current.setPage(4));
    await waitFor(() => expect(get).toHaveBeenCalledTimes(2));
    get.mockResolvedValueOnce(payload(['new']));
    rerender({ q: 'new' });
    expect(result.current.items).toBeUndefined();
    await waitFor(() => expect(result.current.items).toEqual(['new']));
    await act(async () => late.resolve(payload(['late'])));
    expect(result.current.items).toEqual(['new']);
    expect(get).toHaveBeenLastCalledWith(
      '/things?limit=10&offset=0',
      expect.objectContaining({ params: { q: 'new' } })
    );
  });

  it('hides the old account and rejects callbacks retained across account or filter changes', async () => {
    const { result, rerender } = renderHook(({ q }) => usePagedSection(options({ queryKey: q })), {
      initialProps: { q: 'a' },
    });
    await waitFor(() => expect(result.current.items).toEqual(['first']));
    const oldFilter = result.current.setPage;
    rerender({ q: 'b' });
    await waitFor(() => expect(get).toHaveBeenCalledTimes(2));
    rerender({ q: 'a' });
    await waitFor(() => expect(get).toHaveBeenCalledTimes(3));
    act(() => oldFilter(4));
    expect(result.current.page).toBe(1);
    const oldOwner = { page: result.current.setPage, refresh: result.current.refetch };
    const next = delayed();
    get.mockReturnValueOnce(next.promise);
    useAuth.mockReturnValue({ user: { id: 'two' } });
    rerender({ q: 'a' });
    expect(result.current.items).toBeUndefined();
    act(() => {
      oldOwner.page(4);
      oldOwner.refresh();
    });
    await waitFor(() => expect(get).toHaveBeenCalledTimes(4));
    await act(async () => next.resolve(payload(['owner-two'])));
    expect(result.current.items).toEqual(['owner-two']);
    expect(result.current.page).toBe(1);
  });

  it('does no folded read, reopens on the first page and never calls a closed refresh', async () => {
    const { result, rerender } = renderHook(
      ({ enabled }) => usePagedSection(options({ enabled })),
      { initialProps: { enabled: false } }
    );
    await act(async () => {
      result.current.refetch();
    });
    expect(get).not.toHaveBeenCalled();
    rerender({ enabled: true });
    await waitFor(() => expect(result.current.items).toEqual(['first']));
    get.mockResolvedValueOnce(payload(['fourth']));
    act(() => result.current.setPage(4));
    await waitFor(() => expect(result.current.items).toEqual(['fourth']));
    rerender({ enabled: false });
    act(() => result.current.refetch());
    expect(get).toHaveBeenCalledTimes(2);
    rerender({ enabled: true });
    await waitFor(() => expect(get).toHaveBeenCalledTimes(3));
    expect(get.mock.lastCall?.[0]).toBe('/things?limit=10&offset=0');
  });

  it('labels retained rows by their loaded page while navigating and after a failure', async () => {
    const { result } = renderHook(() => usePagedSection(options()));
    await waitFor(() => expect(result.current.items).toEqual(['first']));
    const second = delayed();
    get.mockReturnValueOnce(second.promise);
    act(() => result.current.setPage(2));
    await waitFor(() => expect(result.current.loading).toBe(true));
    expect(result.current.page).toBe(1);
    expect(result.current.firstLoad).toBe(false);
    await act(async () => second.resolve(payload(['second'])));
    expect(result.current.page).toBe(2);
    get.mockRejectedValueOnce(new Error('offline'));
    act(() => result.current.setPage(3));
    await waitFor(() => expect(result.current.error).not.toBeNull());
    expect(result.current.page).toBe(2);
    expect(result.current.items).toEqual(['second']);
    get.mockResolvedValueOnce(payload(['third']));
    act(() => result.current.setPage(3));
    await waitFor(() => expect(result.current.items).toEqual(['third']));
    expect(result.current.page).toBe(3);
  });

  it.each(['manual', 'signal'] as const)(
    'refreshes from page one after a %s refresh, preserving rows meanwhile',
    async kind => {
      const { result, rerender } = renderHook(
        ({ refreshKey }) => usePagedSection(options({ refreshKey })),
        { initialProps: { refreshKey: 0 } }
      );
      await waitFor(() => expect(result.current.items).toEqual(['first']));
      get.mockResolvedValueOnce(payload(['third']));
      act(() => result.current.setPage(3));
      await waitFor(() => expect(result.current.items).toEqual(['third']));
      const first = delayed();
      get.mockReturnValueOnce(first.promise);
      if (kind === 'manual') act(() => result.current.refetch());
      else rerender({ refreshKey: 1 });
      expect(result.current.items).toEqual(['third']);
      await waitFor(() => expect(get.mock.lastCall?.[0]).toBe('/things?limit=10&offset=0'));
      await act(async () => first.resolve(payload(['fresh'], 1)));
      expect(result.current.page).toBe(1);
      expect(result.current.total).toBe(1);
    }
  );

  it('recovers an emptied server page only after its successful response and preserves exact totals', async () => {
    const { result } = renderHook(() => usePagedSection(options()));
    await waitFor(() => expect(result.current.total).toBe(35));
    const empty = delayed();
    get.mockReturnValueOnce(empty.promise);
    act(() => result.current.setPage(4));
    await waitFor(() => expect(get).toHaveBeenCalledTimes(2));
    expect(result.current.total).toBe(35);
    get.mockResolvedValueOnce(payload(['last'], 21));
    await act(async () => empty.resolve(payload([], 21)));
    await waitFor(() => expect(result.current.items).toEqual(['last']));
    expect(result.current.page).toBe(3);
    expect(result.current.totalPages).toBe(3);
  });

  it('keeps initial error distinct from loading and zero results', async () => {
    get.mockRejectedValueOnce(new Error('offline'));
    const { result } = renderHook(() => usePagedSection(options()));
    expect(result.current.firstLoad).toBe(true);
    await waitFor(() => expect(result.current.error).not.toBeNull());
    expect(result.current.firstLoad).toBe(false);
    expect(result.current.items).toBeUndefined();
    get.mockResolvedValueOnce(payload([], 0));
    act(() => result.current.refetch());
    await waitFor(() => expect(result.current.items).toEqual([]));
    expect(result.current.total).toBe(0);
    expect(result.current.totalPages).toBe(1);
    act(() => result.current.setPage(-2));
    expect(result.current.page).toBe(1);
  });

  it('paginates a complete client collection locally and recovers after a shrink', async () => {
    const rows = Array.from({ length: 22 }, (_, i) => String(i));
    get.mockResolvedValueOnce(payload(rows, rows.length));
    const { result } = renderHook(() =>
      usePagedSection(options({ pagination: 'client', path: '/all?active=true' }))
    );
    await waitFor(() => expect(result.current.items).toEqual(rows.slice(0, 10)));
    expect(get.mock.lastCall?.[0]).toBe('/all?active=true');
    act(() => result.current.setPage(3));
    expect(result.current.items).toEqual(rows.slice(20));
    expect(get).toHaveBeenCalledTimes(1);
    get.mockRejectedValueOnce(new Error('offline'));
    act(() => result.current.refetch());
    await waitFor(() => expect(result.current.error).not.toBeNull());
    expect(result.current.items).toEqual(rows.slice(20));
    expect(result.current.page).toBe(3);
    get.mockResolvedValueOnce(payload(['only'], 1));
    act(() => result.current.refetch());
    await waitFor(() => expect(result.current.items).toEqual(['only']));
    expect(result.current.page).toBe(1);
  });

  it('appends paging to existing query parameters without losing them', async () => {
    renderHook(() => usePagedSection(options({ path: '/things?active=true' })));
    await waitFor(() =>
      expect(get.mock.lastCall?.[0]).toBe('/things?active=true&limit=10&offset=0')
    );
  });
});
