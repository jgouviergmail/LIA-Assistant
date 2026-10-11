import { act, renderHook, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { publishApplicationResources } from '@/lib/application-resources';
import type { RAGSpaceListResponse } from '@/types/rag-spaces';

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
import { useActiveSpaces, useSpaceDetail, useSpaces } from '../useSpaces';

const saved: RAGSpaceListResponse = {
  spaces: [
    {
      id: 'space',
      name: 'Saved',
      description: null,
      is_active: true,
      kind: null,
      document_count: 0,
      ready_document_count: 0,
      total_size: 0,
      created_at: '2026-10-01T00:00:00Z',
      updated_at: '2026-10-01T00:00:00Z',
    },
  ],
  total: 1,
};
beforeEach(() => {
  vi.resetAllMocks();
  useAuth.mockReturnValue({ user: { id: 'one' } });
  get.mockResolvedValue(saved);
});

describe('knowledge-space data and assistant refresh belong to the current account', () => {
  it('does not refresh a detail reader without a selected space', async () => {
    renderHook(() => useSpaceDetail(null));
    act(() => publishApplicationResources('one', new Set(['spaces'])));
    await act(async () => {
      await Promise.resolve();
    });
    expect(get).not.toHaveBeenCalled();
  });
  it('rereads all three source readers only for the committed owner', async () => {
    get.mockImplementation(async (url: string) =>
      url.endsWith('/space')
        ? { ...saved.spaces[0], documents: [], drive_sources: [], mail_sources: [] }
        : saved
    );
    const { result } = renderHook(() => ({
      board: useSpaces(),
      active: useActiveSpaces(),
      detail: useSpaceDetail('space'),
    }));
    await waitFor(() => expect(result.current.detail.space?.id).toBe('space'));
    await waitFor(() => expect(result.current.board.total).toBe(1));
    get.mockClear();
    act(() => publishApplicationResources('foreign', new Set(['spaces'])));
    expect(get).not.toHaveBeenCalled();
    act(() => publishApplicationResources('one', new Set(['spaces'])));
    await waitFor(() => expect(get).toHaveBeenCalledTimes(3));
    expect(get.mock.calls.map(call => call[0]).sort()).toEqual([
      '/rag-spaces',
      '/rag-spaces',
      '/rag-spaces/space',
    ]);
  });

  it('hides prior account data and rejects its retired mutations', async () => {
    const { result, rerender } = renderHook(() => useSpaces());
    await waitFor(() => expect(result.current.total).toBe(1));
    const retired = {
      create: result.current.createSpace,
      update: result.current.updateSpace,
      remove: result.current.deleteSpace,
      toggle: result.current.toggleSpace,
    };
    get.mockReturnValue(new Promise(() => {}));
    useAuth.mockReturnValue({ user: { id: 'two' } });
    rerender();
    expect(result.current.spaces).toEqual([]);
    await act(async () => {
      await retired.create({ name: 'Retired' });
      await retired.update('space', { name: 'Retired' });
      await retired.remove('space');
      await retired.toggle('space');
    });
    expect(post).not.toHaveBeenCalled();
    expect(patch).not.toHaveBeenCalled();
    expect(remove).not.toHaveBeenCalled();
  });
});
