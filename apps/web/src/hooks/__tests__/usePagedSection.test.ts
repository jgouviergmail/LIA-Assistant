/**
 * usePagedSection — the paging contract every hub section shares.
 *
 * Four rules, each of which was got wrong somewhere in this codebase before:
 * a closed section costs no request; the total is the payload's, never the
 * page's length; the first-load spinner is keyed on the ABSENCE of data (a
 * refetch clears `error` and a spinner keyed on it unmounts the list
 * mid-refresh); and closing forgets the position.
 */

import { describe, it, expect, vi, beforeEach } from 'vitest';
import { renderHook, act, waitFor } from '@testing-library/react';

const { useApiQuery } = vi.hoisted(() => ({ useApiQuery: vi.fn() }));
vi.mock('@/hooks/useApiQuery', () => ({ useApiQuery }));

import { usePagedSection, HUB_PAGE_SIZE } from '../usePagedSection';

interface Payload {
  rows: string[];
  total: number;
}

function answer(payload: Payload | undefined, over: Record<string, unknown> = {}) {
  useApiQuery.mockReturnValue({
    data: payload,
    loading: payload === undefined,
    error: null,
    refetch: vi.fn(),
    ...over,
  });
}

function render(enabled = true) {
  return renderHook(
    ({ on }: { on: boolean }) =>
      usePagedSection<Payload, string>({
        path: '/things',
        selectItems: p => p.rows,
        selectTotal: p => p.total,
        enabled: on,
      }),
    { initialProps: { on: enabled } }
  );
}

beforeEach(() => {
  useApiQuery.mockReset();
});

describe('usePagedSection', () => {
  it('asks for the first page with the shared size', () => {
    answer({ rows: ['a'], total: 1 });

    render();

    expect(useApiQuery).toHaveBeenCalledWith(
      `/things?limit=${HUB_PAGE_SIZE}&offset=0`,
      expect.objectContaining({ enabled: true })
    );
  });

  it('does not fetch while the section is closed', () => {
    answer(undefined);

    render(false);

    expect(useApiQuery).toHaveBeenCalledWith(
      expect.any(String),
      expect.objectContaining({ enabled: false })
    );
  });

  it('walks pages by offset, not by slicing what it already has', async () => {
    answer({ rows: ['a'], total: 40 });
    const { result } = render();

    act(() => result.current.setPage(3));

    await waitFor(() =>
      expect(useApiQuery).toHaveBeenLastCalledWith(
        `/things?limit=${HUB_PAGE_SIZE}&offset=${HUB_PAGE_SIZE * 2}`,
        expect.anything()
      )
    );
  });

  it('reports the payload total, never the length of the page', () => {
    answer({ rows: ['a', 'b'], total: 214 });

    const { result } = render();

    expect(result.current.items).toHaveLength(2);
    expect(result.current.total).toBe(214);
    expect(result.current.totalPages).toBe(Math.ceil(214 / HUB_PAGE_SIZE));
  });

  it('keeps one page even when the set is empty', () => {
    answer({ rows: [], total: 0 });

    const { result } = render();

    expect(result.current.totalPages).toBe(1);
  });

  it('flags the first load, and never a refetch', () => {
    answer(undefined, { loading: true });
    const first = render();
    expect(first.result.current.firstLoad).toBe(true);

    // Data in hand and loading again: that is a REFETCH, and unmounting the
    // list here is what wipes a reader's place.
    answer({ rows: ['a'], total: 1 }, { loading: true });
    const refetching = render();
    expect(refetching.result.current.firstLoad).toBe(false);
    expect(refetching.result.current.loading).toBe(true);
  });

  it('does not treat an error as a first load', () => {
    // `error` is cleared by a refetch; deriving the spinner from it would
    // remount the list under the reader.
    answer({ rows: ['a'], total: 1 }, { error: new Error('boom') });

    const { result } = render();

    expect(result.current.firstLoad).toBe(false);
    expect(result.current.error).toBeInstanceOf(Error);
    expect(result.current.items).toHaveLength(1);
  });

  it('forgets the position when the section closes', async () => {
    answer({ rows: ['a'], total: 100 });
    const { result, rerender } = render();

    act(() => result.current.setPage(4));
    await waitFor(() => expect(result.current.page).toBe(4));

    rerender({ on: false });

    await waitFor(() => expect(result.current.page).toBe(1));
  });

  it('never asks for a page below the first', () => {
    answer({ rows: [], total: 0 });
    const { result } = render();

    act(() => result.current.setPage(0));

    expect(result.current.page).toBe(1);
  });

  it('appends its paging to a path that already carries a query', () => {
    answer({ rows: [], total: 0 });

    renderHook(() =>
      usePagedSection<Payload, string>({
        path: '/things?kind=peer',
        selectItems: p => p.rows,
        selectTotal: p => p.total,
        enabled: true,
      })
    );

    expect(useApiQuery).toHaveBeenCalledWith(
      `/things?kind=peer&limit=${HUB_PAGE_SIZE}&offset=0`,
      expect.anything()
    );
  });
});
