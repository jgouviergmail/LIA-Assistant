/**
 * useRelationsOverview — the favorites star verb.
 *
 * What must hold: the star flips OPTIMISTICALLY before the network answers;
 * a success keeps it and refetches the overview; a failure rolls the flip
 * back and reports `{ ok: false }` (the caller toasts). The verb result is
 * returned, never left to a post-await state read (peers-hook doctrine).
 */

import { act, renderHook, waitFor } from '@testing-library/react';
import { describe, expect, it, vi, beforeEach } from 'vitest';

const { useApiQuery, refetch } = vi.hoisted(() => ({
  useApiQuery: vi.fn(),
  refetch: vi.fn(),
}));
vi.mock('@/hooks/useApiQuery', () => ({ useApiQuery }));

const { putMutate, delMutate } = vi.hoisted(() => ({
  putMutate: vi.fn(async () => undefined),
  delMutate: vi.fn(async () => undefined),
}));
vi.mock('@/hooks/useApiMutation', () => ({
  useApiMutation: ({ method }: { method: string }) => ({
    mutate: method === 'PUT' ? putMutate : delMutate,
    loading: false,
  }),
}));

import { useRelationsOverview, type RelationSummary } from '../useRelations';

function summary(over: Partial<RelationSummary> = {}): RelationSummary {
  return {
    display_name: 'Ana Lima',
    identity_confidence: 'exact',
    open_loops_count: 0,
    calls_count: 1,
    last_interaction_at: '2026-07-28T09:00:00Z',
    is_favorite: false,
    is_peer: false,
    ...over,
  };
}

beforeEach(() => {
  vi.clearAllMocks();
  useApiQuery.mockReturnValue({
    data: { relations: [summary()] },
    loading: false,
    error: null,
    refetch,
  });
});

describe('useRelationsOverview — toggleFavorite', () => {
  it('flips optimistically while in flight, then hands over to the server truth', async () => {
    let resolvePut: () => void = () => undefined;
    putMutate.mockImplementationOnce(
      () => new Promise<undefined>(resolve => (resolvePut = () => resolve(undefined)))
    );
    const { result, rerender } = renderHook(() => useRelationsOverview());
    // The refetch delivers the fresh server truth (starred) when it runs.
    refetch.mockImplementation(() => {
      useApiQuery.mockReturnValue({
        data: { relations: [summary({ is_favorite: true })] },
        loading: false,
        error: null,
        refetch,
      });
      rerender();
    });

    let outcome: Promise<{ ok: boolean }> | undefined;
    act(() => {
      outcome = result.current.toggleFavorite('Ana Lima', true);
    });
    // In flight: the optimistic flip is already visible.
    expect(result.current.relations[0].is_favorite).toBe(true);

    await act(async () => {
      resolvePut();
      await outcome;
    });
    expect(await outcome).toEqual({ ok: true });
    expect(putMutate).toHaveBeenCalledWith('/relations/favorites/Ana%20Lima');
    expect(refetch).toHaveBeenCalled();
    // Reconciled: the server truth carries the star, the override is gone.
    await waitFor(() => expect(result.current.relations[0].is_favorite).toBe(true));
  });

  it('unstars through DELETE and reconciles to the fresh overview', async () => {
    useApiQuery.mockReturnValue({
      data: { relations: [summary({ is_favorite: true })] },
      loading: false,
      error: null,
      refetch,
    });
    const { result, rerender } = renderHook(() => useRelationsOverview());
    refetch.mockImplementation(() => {
      useApiQuery.mockReturnValue({
        data: { relations: [summary({ is_favorite: false })] },
        loading: false,
        error: null,
        refetch,
      });
      rerender();
    });
    await act(async () => {
      await result.current.toggleFavorite('Ana Lima', false);
    });
    expect(delMutate).toHaveBeenCalledWith('/relations/favorites/Ana%20Lima');
    await waitFor(() => expect(result.current.relations[0].is_favorite).toBe(false));
  });

  it('rolls the flip back and reports ok:false when the server refuses', async () => {
    putMutate.mockRejectedValueOnce(new Error('500'));
    const { result } = renderHook(() => useRelationsOverview());
    let outcome: { ok: boolean } | undefined;
    await act(async () => {
      outcome = await result.current.toggleFavorite('Ana Lima', true);
    });
    expect(outcome).toEqual({ ok: false });
    await waitFor(() => expect(result.current.relations[0].is_favorite).toBe(false));
    expect(refetch).not.toHaveBeenCalled();
  });
});
