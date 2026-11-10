/**
 * useWorkbenchPage — one cursor-paged listing of the « Tools » section (ADR-369).
 *
 * Loading is DERIVED from the key (owner, path, params): no frame shows the
 * previous listing as the answer to new params, a late answer to old params is
 * dropped, an owner change clears the list at once. A refresh re-reads page
 * one IN PLACE — what is on screen stays until its answer lands — and a page
 * asked for during a refresh is not appended to the listing that replaces it.
 */

import { beforeEach, describe, expect, it, vi } from 'vitest';

import { act, renderHook, waitFor } from '@/__tests__/test-utils';

const { get } = vi.hoisted(() => ({ get: vi.fn() }));
const { account } = vi.hoisted(() => ({ account: { id: 'account-a' } }));
vi.mock('@/hooks/useAuth', () => ({ useAuth: () => ({ user: account }) }));
vi.mock('@/lib/api-client', async importOriginal => ({
  ...(await importOriginal<typeof import('@/lib/api-client')>()),
  default: { get },
}));

import { useWorkbenchPage } from '../useWorkbenchPage';

interface Row {
  id: string;
  title: string;
}

interface Page {
  items: Row[];
  next_page_token: string | null;
}

function page(ids: readonly string[], next: string | null = null): Page {
  return { items: ids.map(id => ({ id, title: id })), next_page_token: next };
}

/** A GET the test answers by hand. */
function deferred(): { promise: Promise<Page>; answer: (value: Page) => void } {
  let answer!: (value: Page) => void;
  const promise = new Promise<Page>(resolve => {
    answer = resolve;
  });
  return { promise, answer };
}

function ids(rows: readonly Row[]): string[] {
  return rows.map(row => row.id);
}

beforeEach(() => {
  account.id = 'account-a';
  vi.clearAllMocks();
  get.mockResolvedValue(page(['m1', 'm2']));
});

describe('useWorkbenchPage', () => {
  it('reads the first page of the path with its params', async () => {
    const { result } = renderHook(() =>
      useWorkbenchPage<Row>('/workbench/tasks/lists/l1/tasks', { status: 'open' })
    );

    expect(result.current.loading).toBe(true);
    await waitFor(() => expect(ids(result.current.items)).toEqual(['m1', 'm2']));
    expect(result.current.loading).toBe(false);
    expect(get).toHaveBeenCalledWith('/workbench/tasks/lists/l1/tasks', {
      params: { status: 'open' },
      signal: expect.any(AbortSignal),
    });
  });

  it('drops a late answer to the previous params', async () => {
    const first = deferred();
    const second = deferred();
    get.mockReturnValueOnce(first.promise).mockReturnValueOnce(second.promise);
    const { result, rerender } = renderHook(
      ({ folder }) => useWorkbenchPage<Row>('/workbench/mail/messages', { folder }),
      { initialProps: { folder: 'inbox' } }
    );

    rerender({ folder: 'sent' });
    await act(async () => second.answer(page(['s1'])));
    await act(async () => first.answer(page(['i1'])));

    expect(ids(result.current.items)).toEqual(['s1']);
  });

  it('clears the list at once when the account changes', async () => {
    const { result, rerender } = renderHook(() =>
      useWorkbenchPage<Row>('/workbench/mail/messages', {})
    );
    await waitFor(() => expect(result.current.items).toHaveLength(2));

    get.mockReturnValue(deferred().promise);
    account.id = 'account-b';
    rerender();

    expect(result.current.items).toEqual([]);
    expect(result.current.loading).toBe(true);
  });

  it('appends the next page and stops at the last one', async () => {
    get.mockResolvedValueOnce(page(['m1', 'm2'], 't2')).mockResolvedValueOnce(page(['m3']));
    const { result } = renderHook(() => useWorkbenchPage<Row>('/workbench/mail/messages', {}));
    await waitFor(() => expect(result.current.nextToken).toBe('t2'));

    await act(() => result.current.loadMore());
    expect(ids(result.current.items)).toEqual(['m1', 'm2', 'm3']);
    expect(get).toHaveBeenLastCalledWith('/workbench/mail/messages', {
      params: { page_token: 't2' },
    });

    await act(() => result.current.loadMore());
    expect(get).toHaveBeenCalledTimes(2);
  });

  it('asks for the next page once, however often « more » is asked meanwhile', async () => {
    get.mockResolvedValueOnce(page(['m1'], 't2'));
    const { result } = renderHook(() => useWorkbenchPage<Row>('/workbench/mail/messages', {}));
    await waitFor(() => expect(result.current.nextToken).toBe('t2'));
    const next = deferred();
    get.mockReturnValueOnce(next.promise);

    let first: Promise<void> = Promise.resolve();
    let second: Promise<void> = Promise.resolve();
    act(() => {
      first = result.current.loadMore();
      second = result.current.loadMore();
    });
    await act(async () => {
      next.answer(page(['m2']));
      await Promise.all([first, second]);
    });

    expect(ids(result.current.items)).toEqual(['m1', 'm2']);
    expect(get).toHaveBeenCalledTimes(2);
  });

  it('keeps what is on screen until a refresh is answered', async () => {
    const { result } = renderHook(() => useWorkbenchPage<Row>('/workbench/mail/messages', {}));
    await waitFor(() => expect(result.current.items).toHaveLength(2));
    const reread = deferred();
    get.mockReturnValueOnce(reread.promise);

    let done: Promise<void> = Promise.resolve();
    act(() => {
      done = result.current.refresh();
    });
    expect(ids(result.current.items)).toEqual(['m1', 'm2']);
    expect(result.current.loading).toBe(false);

    await act(async () => {
      reread.answer(page(['m2', 'm9']));
      await done;
    });
    expect(ids(result.current.items)).toEqual(['m2', 'm9']);
  });

  it('never appends a page asked for during a refresh', async () => {
    get.mockResolvedValueOnce(page(['m1'], 't2'));
    const { result } = renderHook(() => useWorkbenchPage<Row>('/workbench/mail/messages', {}));
    await waitFor(() => expect(result.current.nextToken).toBe('t2'));
    const reread = deferred();
    get.mockReturnValueOnce(reread.promise);

    act(() => {
      void result.current.refresh();
    });
    await act(() => result.current.loadMore());
    await act(async () => reread.answer(page(['m0', 'm1'])));

    expect(ids(result.current.items)).toEqual(['m0', 'm1']);
    expect(get).toHaveBeenCalledTimes(2);
  });

  it('replaces or removes one item without a read', async () => {
    const { result } = renderHook(() => useWorkbenchPage<Row>('/workbench/mail/messages', {}));
    await waitFor(() => expect(result.current.items).toHaveLength(2));

    act(() => result.current.replaceItem('m1', { id: 'm1', title: 'read' }));
    expect(result.current.items[0]?.title).toBe('read');
    act(() => result.current.replaceItem('m2', null));
    expect(ids(result.current.items)).toEqual(['m1']);
    expect(get).toHaveBeenCalledTimes(1);
  });

  it('keeps an item a link named at the head of the list, once (2026-11-07)', async () => {
    get.mockResolvedValueOnce(page(['m1', 'm2'], 't2')).mockResolvedValueOnce(page(['m9', 'm3']));
    const { result } = renderHook(() => useWorkbenchPage<Row>('/workbench/mail/messages', {}));
    await waitFor(() => expect(result.current.nextToken).toBe('t2'));

    act(() => result.current.keepItem({ id: 'm9', title: 'kept' }));
    act(() => result.current.keepItem({ id: 'm1', title: 'already there' }));
    expect(ids(result.current.items)).toEqual(['m9', 'm1', 'm2']);
    expect(result.current.items[1]?.title).not.toBe('already there');

    // Its own page landing puts it back in its place: never twice.
    await act(() => result.current.loadMore());
    expect(ids(result.current.items)).toEqual(['m1', 'm2', 'm9', 'm3']);
  });

  it('says why the first read failed, and shows nothing', async () => {
    const refused = new Error('down');
    get.mockRejectedValueOnce(refused);
    const { result } = renderHook(() => useWorkbenchPage<Row>('/workbench/mail/messages', {}));

    await waitFor(() => expect(result.current.error).toBe(refused));
    expect(result.current.items).toEqual([]);
    expect(result.current.loading).toBe(false);
  });

  it('counts what the pages read could not show, a refresh starting over (ADR-185)', async () => {
    get
      .mockResolvedValueOnce({ ...page(['m1'], 't2'), skipped: 2 })
      .mockResolvedValueOnce({ ...page(['m2']), skipped: 1 })
      .mockResolvedValueOnce(page(['m1']));
    const { result } = renderHook(() => useWorkbenchPage<Row>('/workbench/mail/messages', {}));
    await waitFor(() => expect(result.current.skipped).toBe(2));

    await act(() => result.current.loadMore());
    expect(result.current.skipped).toBe(3);

    await act(() => result.current.refresh());
    expect(result.current.skipped).toBe(0);
  });

  describe('a re-read nobody asked for', () => {
    const PATH = '/workbench/mail/messages';

    it('replaces the first page in place', async () => {
      const { result } = renderHook(() => useWorkbenchPage<Row>(PATH, {}));
      await waitFor(() => expect(ids(result.current.items)).toEqual(['m1', 'm2']));
      get.mockResolvedValueOnce(page(['m0', 'm1', 'm2']));

      await act(() => result.current.refresh({ unasked: true }));

      expect(ids(result.current.items)).toEqual(['m0', 'm1', 'm2']);
    });

    it('keeps what is on screen when it fails: nobody asked', async () => {
      const { result } = renderHook(() => useWorkbenchPage<Row>(PATH, {}));
      await waitFor(() => expect(ids(result.current.items)).toEqual(['m1', 'm2']));
      get.mockRejectedValueOnce(new Error('offline'));

      await act(() => result.current.refresh({ unasked: true }));

      expect(ids(result.current.items)).toEqual(['m1', 'm2']);
      expect(result.current.error).toBeNull();
    });

    it('never takes back the pages the person went through', async () => {
      get.mockResolvedValueOnce(page(['m1'], 't2')).mockResolvedValueOnce(page(['m2']));
      const { result } = renderHook(() => useWorkbenchPage<Row>(PATH, {}));
      await waitFor(() => expect(result.current.nextToken).toBe('t2'));
      await act(() => result.current.loadMore());
      get.mockClear();

      await act(() => result.current.refresh({ unasked: true }));

      expect(get).not.toHaveBeenCalled();
      expect(ids(result.current.items)).toEqual(['m1', 'm2']);
    });

    it('waits for a first page still on its way', async () => {
      const first = deferred();
      get.mockReturnValueOnce(first.promise);
      const { result } = renderHook(() => useWorkbenchPage<Row>(PATH, {}));

      await act(() => result.current.refresh({ unasked: true }));

      expect(get).toHaveBeenCalledTimes(1);
      await act(async () => first.answer(page(['m1'])));
      expect(ids(result.current.items)).toEqual(['m1']);
    });

    it('never drops a next page on its way', async () => {
      get.mockResolvedValueOnce(page(['m1'], 't2'));
      const { result } = renderHook(() => useWorkbenchPage<Row>(PATH, {}));
      await waitFor(() => expect(result.current.nextToken).toBe('t2'));
      const next = deferred();
      get.mockReturnValueOnce(next.promise);
      let more: Promise<void> = Promise.resolve();
      act(() => {
        more = result.current.loadMore();
      });

      await act(() => result.current.refresh({ unasked: true }));
      await act(async () => {
        next.answer(page(['m2']));
        await more;
      });

      expect(get).toHaveBeenCalledTimes(2);
      expect(ids(result.current.items)).toEqual(['m1', 'm2']);
    });

    it('leaves a failed listing to its own retry', async () => {
      get.mockRejectedValueOnce(new Error('down'));
      const { result } = renderHook(() => useWorkbenchPage<Row>(PATH, {}));
      await waitFor(() => expect(result.current.error).toBeInstanceOf(Error));
      get.mockClear();

      await act(() => result.current.refresh({ unasked: true }));

      expect(get).not.toHaveBeenCalled();
    });
  });

  it('reads nothing without a path', async () => {
    const { result } = renderHook(() => useWorkbenchPage<Row>(null, {}));

    await act(async () => {
      await Promise.resolve();
    });
    expect(get).not.toHaveBeenCalled();
    expect(result.current.loading).toBe(false);
  });
});
