/**
 * useWorkbenchItem — one item of the « Tools » section read by its id (ADR-369):
 * the open message, event, contact or file.
 *
 * Like the listings (`useWorkbenchPage`), loading is DERIVED from the key
 * (owner, path, params): opening another item never shows the previous one as
 * its answer, a late answer to the previous id is dropped, an owner change
 * clears it at once. A refresh re-reads IN PLACE, and a failed one withdraws
 * what was shown (owner rule 2026-10-21).
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

import { useWorkbenchItem } from '../useWorkbenchItem';

interface Item {
  id: string;
  subject: string;
}

function item(id: string, subject = id): Item {
  return { id, subject };
}

/** A GET the test answers by hand. */
function deferred(): { promise: Promise<Item>; answer: (value: Item) => void } {
  let answer!: (value: Item) => void;
  const promise = new Promise<Item>(resolve => {
    answer = resolve;
  });
  return { promise, answer };
}

beforeEach(() => {
  account.id = 'account-a';
  vi.clearAllMocks();
  get.mockImplementation((_path: string, { params }: { params: { id: string } }) =>
    Promise.resolve(item(params.id))
  );
});

describe('useWorkbenchItem', () => {
  it('reads the item the params name', async () => {
    const { result } = renderHook(() =>
      useWorkbenchItem<Item>('/workbench/mail/message', { id: 'm1' })
    );

    await waitFor(() => expect(result.current.item).toEqual(item('m1')));
    expect(get).toHaveBeenCalledWith('/workbench/mail/message', {
      params: { id: 'm1' },
      signal: expect.any(AbortSignal),
    });
    expect(result.current.loading).toBe(false);
  });

  it('never shows the previous item as the answer to another id', async () => {
    const { result, rerender } = renderHook(
      ({ id }) => useWorkbenchItem<Item>('/workbench/mail/message', { id }),
      { initialProps: { id: 'm1' } }
    );
    await waitFor(() => expect(result.current.item?.id).toBe('m1'));
    const pending = deferred();
    get.mockReturnValueOnce(pending.promise);

    rerender({ id: 'm2' });

    expect(result.current.item).toBeUndefined();
    expect(result.current.loading).toBe(true);
    await act(async () => pending.answer(item('m2')));
    expect(result.current.item?.id).toBe('m2');
  });

  it('drops a late answer to the previous id', async () => {
    const late = deferred();
    get.mockReturnValueOnce(late.promise);
    const { result, rerender } = renderHook(
      ({ id }) => useWorkbenchItem<Item>('/workbench/mail/message', { id }),
      { initialProps: { id: 'm1' } }
    );

    rerender({ id: 'm2' });
    await waitFor(() => expect(result.current.item?.id).toBe('m2'));
    await act(async () => late.answer(item('m1')));

    expect(result.current.item?.id).toBe('m2');
  });

  it('clears the item at once when the account changes', async () => {
    const { result, rerender } = renderHook(() =>
      useWorkbenchItem<Item>('/workbench/mail/message', { id: 'm1' })
    );
    await waitFor(() => expect(result.current.item?.id).toBe('m1'));
    get.mockReturnValueOnce(new Promise(() => undefined));

    account.id = 'account-b';
    rerender();

    expect(result.current.item).toBeUndefined();
  });

  it('keeps the item on screen until a refresh is answered, and withdraws it on failure', async () => {
    const { result } = renderHook(() =>
      useWorkbenchItem<Item>('/workbench/mail/message', { id: 'm1' })
    );
    await waitFor(() => expect(result.current.item?.id).toBe('m1'));
    const pending = deferred();
    get.mockReturnValueOnce(pending.promise);

    let refreshed!: Promise<void>;
    act(() => {
      refreshed = result.current.refresh();
    });
    expect(result.current.item?.subject).toBe('m1');
    await act(async () => {
      pending.answer(item('m1', 'edited'));
      await refreshed;
    });
    expect(result.current.item?.subject).toBe('edited');

    get.mockRejectedValueOnce(new Error('gone'));
    await act(() => result.current.refresh());
    expect(result.current.item).toBeUndefined();
    expect(result.current.error).toBeInstanceOf(Error);
  });

  describe('a re-read nobody asked for', () => {
    const PATH = '/workbench/mail/message';

    it('replaces the item in place', async () => {
      const { result } = renderHook(() => useWorkbenchItem<Item>(PATH, { id: 'm1' }));
      await waitFor(() => expect(result.current.item?.id).toBe('m1'));
      get.mockResolvedValueOnce(item('m1', 'edited'));

      await act(() => result.current.refresh({ unasked: true }));

      expect(result.current.item?.subject).toBe('edited');
    });

    it('keeps what is on screen when it fails: nobody asked', async () => {
      const { result } = renderHook(() => useWorkbenchItem<Item>(PATH, { id: 'm1' }));
      await waitFor(() => expect(result.current.item?.id).toBe('m1'));
      get.mockRejectedValueOnce(new Error('offline'));

      await act(() => result.current.refresh({ unasked: true }));

      expect(result.current.item?.id).toBe('m1');
      expect(result.current.error).toBeNull();
    });

    it('waits for a first read still on its way', async () => {
      const first = deferred();
      get.mockReturnValueOnce(first.promise);
      const { result } = renderHook(() => useWorkbenchItem<Item>(PATH, { id: 'm1' }));

      await act(() => result.current.refresh({ unasked: true }));

      expect(get).toHaveBeenCalledTimes(1);
      await act(async () => first.answer(item('m1')));
      expect(result.current.item?.id).toBe('m1');
    });

    it('leaves a failed read to its own retry', async () => {
      get.mockRejectedValueOnce(new Error('down'));
      const { result } = renderHook(() => useWorkbenchItem<Item>(PATH, { id: 'm1' }));
      await waitFor(() => expect(result.current.error).toBeInstanceOf(Error));
      get.mockClear();

      await act(() => result.current.refresh({ unasked: true }));

      expect(get).not.toHaveBeenCalled();
    });
  });

  it('applies a change to the item without a read', async () => {
    const { result } = renderHook(() =>
      useWorkbenchItem<Item>('/workbench/mail/message', { id: 'm1' })
    );
    await waitFor(() => expect(result.current.item?.id).toBe('m1'));

    act(() => result.current.setItem(current => ({ ...current, subject: 'read' })));

    expect(result.current.item?.subject).toBe('read');
    expect(get).toHaveBeenCalledTimes(1);
  });

  it('reads nothing without a path', async () => {
    const { result } = renderHook(() => useWorkbenchItem<Item>(null, { id: 'm1' }));

    await act(async () => {
      await Promise.resolve();
    });
    expect(get).not.toHaveBeenCalled();
    expect(result.current.loading).toBe(false);
    expect(result.current.item).toBeUndefined();
  });
});
