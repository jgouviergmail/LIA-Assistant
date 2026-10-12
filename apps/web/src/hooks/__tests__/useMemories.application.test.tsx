import { act, renderHook, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { publishApplicationResources } from '@/lib/application-resources';

const { get, post, patch, remove, useAuth } = vi.hoisted(() => ({
  get: vi.fn(),
  post: vi.fn(),
  patch: vi.fn(),
  remove: vi.fn(),
  useAuth: vi.fn(),
}));
vi.mock('@/hooks/useAuth', () => ({ useAuth }));
vi.mock('@/lib/api-client', async importOriginal => {
  const original = await importOriginal<typeof import('@/lib/api-client')>();
  return { ...original, default: { get, post, patch, delete: remove } };
});
import { useMemories } from '../useMemories';

const saved = {
  items: [{ id: 'memory', content: 'Owned fact', category: 'personal', pinned: false }],
  total: 1,
  by_category: { personal: 1 },
};
beforeEach(() => {
  vi.resetAllMocks();
  useAuth.mockReturnValue({ user: { id: 'one' } });
  get.mockImplementation((endpoint: string) =>
    Promise.resolve(endpoint === '/memories/categories' ? { categories: [] } : saved)
  );
});

describe('memory invalidation belongs to its account', () => {
  it('rereads a confirmed pin only for its owner without hiding loaded content', async () => {
    const { result } = renderHook(() => useMemories());
    await waitFor(() => expect(result.current.memories).toHaveLength(1));
    get.mockClear();
    act(() => publishApplicationResources('foreign', new Set(['memories'])));
    expect(get).not.toHaveBeenCalled();
    let complete: ((value: typeof saved) => void) | undefined;
    get.mockImplementation(
      () =>
        new Promise<typeof saved>(resolve => {
          complete = resolve;
        })
    );
    act(() => publishApplicationResources('one', new Set(['memories'])));
    await waitFor(() => expect(get).toHaveBeenCalledOnce());
    expect(result.current.memories).toHaveLength(1);
    expect(result.current.loading).toBe(false);
    await act(async () => complete?.({ ...saved, items: [{ ...saved.items[0], pinned: true }] }));
    await waitFor(() => expect(result.current.memories[0].pinned).toBe(true));
  });

  it('hides retired data and refuses retired mutation callbacks after switching accounts', async () => {
    const { result, rerender } = renderHook(() => useMemories());
    await waitFor(() => expect(result.current.memories).toHaveLength(1));
    const retired = result.current;
    get.mockReturnValue(new Promise(() => {}));
    useAuth.mockReturnValue({ user: { id: 'two' } });
    rerender();
    expect(result.current.memories).toEqual([]);
    await act(async () => {
      await retired.createMemory({ content: 'Old', category: 'personal' });
      await retired.updateMemory('memory', { content: 'Old' });
      await retired.deleteMemory('memory');
      await retired.deleteAllMemories();
      await retired.togglePin('memory', true);
    });
    expect(post).not.toHaveBeenCalled();
    expect(patch).not.toHaveBeenCalled();
    expect(remove).not.toHaveBeenCalled();
  });

  it('keeps the active category when rereading a confirmed change', async () => {
    const { result } = renderHook(() => useMemories());
    await waitFor(() => expect(result.current.memories).toHaveLength(1));
    act(() => result.current.setCategoryFilter('personal'));
    await waitFor(() =>
      expect(get).toHaveBeenCalledWith(
        expect.stringContaining('category=personal'),
        expect.anything()
      )
    );
    get.mockClear();
    act(() => publishApplicationResources('one', new Set(['memories'])));
    await waitFor(() =>
      expect(get).toHaveBeenCalledWith('/memories?category=personal', expect.anything())
    );
  });
});
