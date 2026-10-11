import { act, renderHook, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { publishApplicationResources } from '@/lib/application-resources';
import type { BookmarkList } from '@/types/bookmarks';

const { get, useAuth } = vi.hoisted(() => ({ get: vi.fn(), useAuth: vi.fn() }));
vi.mock('@/hooks/useAuth', () => ({ useAuth }));
vi.mock('@/lib/api-client', async importOriginal => {
  const original = await importOriginal<typeof import('@/lib/api-client')>();
  return { ...original, default: { get } };
});
import { useBookmarks } from '../useBookmarks';

const saved: BookmarkList = {
  items: [{ id: 'aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa', content: 'Owned answer',
    message_id: null, conversation_id: null, request_content: null,
    answered_at: '2026-10-10T00:00:00Z', created_at: '2026-10-10T00:00:00Z',
    index_state: null, indexed_at: null, index_usage: null, answer_usage: null }],
  total: 1, limit: 24, offset: 0, max_limit: 100, max_per_user: 100,
};
beforeEach(() => {
  vi.resetAllMocks();
  useAuth.mockReturnValue({ user: { id: 'one' } });
  get.mockResolvedValue(saved);
});

describe('saved answer changes and queries belong to their current account', () => {
  it('refreshes only the committed owner and retains filters', async () => {
    const { result } = renderHook(() => useBookmarks('literal', true));
    await waitFor(() => expect(result.current.total).toBe(1));
    get.mockClear();
    act(() => publishApplicationResources('foreign', new Set(['generated_assets'])));
    expect(get).not.toHaveBeenCalled();
    act(() => publishApplicationResources('one', new Set(['generated_assets'])));
    await waitFor(() => expect(get).toHaveBeenCalledTimes(1));
    expect(get.mock.calls[0][0]).toContain('q=literal');
  });

  it('hides the previous account while a new owned request is pending', async () => {
    const { result, rerender } = renderHook(() => useBookmarks(undefined, true));
    await waitFor(() => expect(result.current.total).toBe(1));
    let resolve: (value: BookmarkList) => void = () => {};
    get.mockImplementation(() => new Promise<BookmarkList>(accept => { resolve = accept; }));
    useAuth.mockReturnValue({ user: { id: 'two' } });
    rerender();
    expect(result.current.total).toBe(0);
    expect(result.current.maxPerUser).toBe(0);
    expect(result.current.items).toEqual([]);
    await waitFor(() => expect(get).toHaveBeenCalledTimes(2));
    await act(async () => { resolve({ ...saved, total: 2 }); });
    await waitFor(() => expect(result.current.total).toBe(2));
  });

  it('never queries an unavailable account', async () => {
    useAuth.mockReturnValue({ user: null });
    renderHook(() => useBookmarks(undefined, true));
    await act(async () => { await Promise.resolve(); });
    expect(get).not.toHaveBeenCalled();
  });

  it('exposes a failed initial read instead of an endless loading state', async () => {
    get.mockRejectedValue(new Error('Controlled query failure'));
    const { result } = renderHook(() => useBookmarks(undefined, true));
    await waitFor(() => expect(result.current.error).toBeTruthy());
    expect(result.current.firstLoad).toBe(false);
    expect(result.current.loading).toBe(false);
  });
});
