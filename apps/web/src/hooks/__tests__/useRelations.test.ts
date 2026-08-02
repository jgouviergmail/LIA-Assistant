/**
 * useRelations — the CRM's two read hooks and its one write verb.
 *
 * What must hold:
 * - the star flips OPTIMISTICALLY before the network answers; a success keeps
 *   it and refetches the overview; a failure rolls the flip back and reports
 *   `{ ok: false }` (the caller toasts). The verb result is returned, never
 *   left to a post-await state read (peers-hook doctrine);
 * - the detail hook asks for nothing while no relationship is selected, and
 *   reports failure as a boolean rather than leaking a raw error object.
 */

import { act, renderHook, waitFor } from '@testing-library/react';
import { describe, expect, it, vi, beforeEach } from 'vitest';

const { useApiQuery, refetch } = vi.hoisted(() => ({
  useApiQuery: vi.fn(),
  refetch: vi.fn(),
}));
vi.mock('@/hooks/useApiQuery', () => ({ useApiQuery }));

const { apiGet } = vi.hoisted(() => ({ apiGet: vi.fn() }));
vi.mock('@/lib/api-client', () => ({
  apiClient: { get: apiGet },
  ApiError: class ApiError extends Error {},
}));

const { putMutate, delMutate, postMutate } = vi.hoisted(() => ({
  // `Promise<unknown>`, not `Promise<undefined>`: the scope PUT answers with
  // the stored scope, and a mock that can only resolve `undefined` could not
  // express the echo the caller adopts.
  putMutate: vi.fn(async (): Promise<unknown> => undefined),
  delMutate: vi.fn(async (): Promise<unknown> => undefined),
  postMutate: vi.fn(async (): Promise<unknown> => undefined),
}));
vi.mock('@/hooks/useApiMutation', () => ({
  useApiMutation: ({ method }: { method: string }) => ({
    mutate: method === 'PUT' ? putMutate : method === 'POST' ? postMutate : delMutate,
    loading: false,
  }),
}));

import {
  useRelationContext,
  useRelationDetail,
  useRelationMerge,
  useRelationsOverview,
  useOverviewScope,
  type RelationDetail,
  type RelationSummary,
} from '../useRelations';

function summary(over: Partial<RelationSummary> = {}): RelationSummary {
  return {
    display_name: 'Ana Lima',
    identity_confidence: 'exact',
    open_loops_count: 0,
    calls_count: 1,
    peer_messages_count: 0,
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

describe('useRelationsOverview — initialLoading', () => {
  it('is true only before the first answer', () => {
    useApiQuery.mockReturnValue({ data: undefined, loading: true, error: null, refetch });
    const { result } = renderHook(() => useRelationsOverview());
    expect(result.current.initialLoading).toBe(true);
  });

  it('is false while the post-star refetch runs, so the list never unmounts', () => {
    // Regression guard: starring refetches the overview, and swapping the
    // whole list for a spinner then wiped the toolbar the user was using —
    // their search text, their sort choice and their filter chips.
    useApiQuery.mockReturnValue({
      data: { relations: [summary()] },
      loading: true,
      error: null,
      refetch,
    });
    const { result } = renderHook(() => useRelationsOverview());
    expect(result.current.loading).toBe(true);
    expect(result.current.initialLoading).toBe(false);
    expect(result.current.relations).toHaveLength(1);
  });

  it('is false when the first load failed, so the empty state can be shown', () => {
    useApiQuery.mockReturnValue({
      data: undefined,
      loading: false,
      error: new Error('boom'),
      refetch,
    });
    const { result } = renderHook(() => useRelationsOverview());
    expect(result.current.initialLoading).toBe(false);
    expect(result.current.relations).toEqual([]);
  });
});

describe('useRelationDetail', () => {
  const detail: RelationDetail = {
    display_name: 'Ana Lima',
    identity_confidence: 'exact',
    merged_from: [],
    open_loops: [],
    open_loops_total: 0,
    recent_calls: [],
    recent_calls_total: 0,
    memories: [],
    memories_total: 0,
    peer_messages: [
      { id: 'pm1', direction: 'received', content: 'Salut !', occurred_at: '2026-07-29T10:00:00Z' },
    ],
    peer_messages_total: 1,
    peer_link: null,
    is_favorite: false,
    is_peer: true,
  };

  it('fetches the named relationship and surfaces its relayed messages', () => {
    useApiQuery.mockReturnValue({ data: detail, loading: false, error: null, refetch });
    const { result } = renderHook(() => useRelationDetail('Gérard Dupont'));

    expect(useApiQuery).toHaveBeenCalledWith(
      '/relations/G%C3%A9rard%20Dupont',
      expect.objectContaining({ enabled: true })
    );
    expect(result.current.detail?.peer_messages).toHaveLength(1);
    expect(result.current.error).toBe(false);
  });

  it('asks for nothing while no relationship is selected', () => {
    useApiQuery.mockReturnValue({ data: undefined, loading: false, error: null, refetch });
    const { result } = renderHook(() => useRelationDetail(null));

    expect(useApiQuery).toHaveBeenCalledWith('', expect.objectContaining({ enabled: false }));
    expect(result.current.detail).toBeNull();
  });

  it('reports an error as a boolean, never as a raw error object', () => {
    useApiQuery.mockReturnValue({
      data: undefined,
      loading: false,
      error: new Error('boom'),
      refetch,
    });
    const { result } = renderHook(() => useRelationDetail('Ana'));
    expect(result.current.error).toBe(true);
    expect(result.current.detail).toBeNull();
  });
});

describe('useRelationContext', () => {
  it('reads the provider sections from their OWN endpoint', () => {
    // Separate from the detail on purpose: the connectors are slow and
    // fallible, and the 360° view must be on screen long before they answer.
    useApiQuery.mockReturnValue({
      data: undefined,
      loading: true,
      error: null,
      refetch,
      setData: vi.fn(),
    });
    renderHook(() => useRelationContext('Ana Lima'));

    expect(useApiQuery).toHaveBeenCalledWith(
      '/relations/Ana%20Lima/context',
      expect.objectContaining({ enabled: true })
    );
  });

  describe('refreshSections', () => {
    it('asks ONCE with the sections, and never sticks them onto the query', async () => {
      // Baked into the query key, `?refresh=` would make every later refetch
      // bypass the cache too: a control meant to be pressed once would become
      // "never use the cache again", spending provider quota for good.
      const setData = vi.fn();
      apiGet.mockResolvedValueOnce({ contact: 'fresh' });
      useApiQuery.mockReturnValue({
        data: { contact: 'stale' },
        loading: false,
        error: null,
        refetch,
        setData,
      });
      const { result } = renderHook(() => useRelationContext('Ana Lima'));

      await act(async () => {
        await result.current.refreshSections(['contact', 'emails']);
      });

      expect(apiGet).toHaveBeenCalledWith('/relations/Ana%20Lima/context?refresh=contact,emails');
      expect(setData).toHaveBeenCalledWith({ contact: 'fresh' });
      expect(useApiQuery).toHaveBeenCalledWith('/relations/Ana%20Lima/context', expect.anything());
    });

    it('keeps the current answer when the refresh fails', async () => {
      // Replacing it with nothing would turn "could not look again" into
      // "found nothing".
      const setData = vi.fn();
      apiGet.mockRejectedValueOnce(new Error('boom'));
      useApiQuery.mockReturnValue({
        data: { contact: 'stale' },
        loading: false,
        error: null,
        refetch,
        setData,
      });
      const { result } = renderHook(() => useRelationContext('Ana Lima'));

      await act(async () => {
        await result.current.refreshSections(['contact']);
      });

      expect(setData).not.toHaveBeenCalled();
      expect(result.current.context).toEqual({ contact: 'stale' });
    });

    it('asks nothing when no relationship is selected', async () => {
      useApiQuery.mockReturnValue({
        data: undefined,
        loading: false,
        error: null,
        refetch,
        setData: vi.fn(),
      });
      const { result } = renderHook(() => useRelationContext(null));
      await act(async () => {
        await result.current.refreshSections(['contact']);
      });
      expect(apiGet).not.toHaveBeenCalled();
    });
  });

  it('asks for nothing while no relationship is selected', () => {
    useApiQuery.mockReturnValue({
      data: undefined,
      loading: false,
      error: null,
      refetch,
      setData: vi.fn(),
    });
    const { result } = renderHook(() => useRelationContext(null));

    expect(useApiQuery).toHaveBeenCalledWith('', expect.objectContaining({ enabled: false }));
    expect(result.current.context).toBeNull();
  });

  it('reports an error as a boolean, never as a raw error object', () => {
    useApiQuery.mockReturnValue({
      data: undefined,
      loading: false,
      error: new Error('boom'),
      refetch,
      setData: vi.fn(),
    });
    const { result } = renderHook(() => useRelationContext('Ana'));
    expect(result.current.error).toBe(true);
    expect(result.current.context).toBeNull();
  });
});

describe('useOverviewScope', () => {
  it('adopts the ECHO the server returns, not what it sent', async () => {
    // A value the server clamped is what must pre-fill the panel next time;
    // storing the request instead would show a number that never applied.
    const setData = vi.fn();
    useApiQuery.mockReturnValue({
      data: { sections: ['contact'], directions: [], roles: [], max_items: 5 },
      loading: false,
      error: null,
      refetch,
      setData,
    });
    putMutate.mockResolvedValueOnce({
      sections: ['contact'],
      directions: [],
      roles: [],
      max_items: 25,
    });

    const { result } = renderHook(() => useOverviewScope());
    let ok: boolean | undefined;
    await act(async () => {
      ok = await result.current.save({
        sections: ['contact'],
        directions: [],
        roles: [],
        max_items: 999,
      });
    });

    expect(ok).toBe(true);
    expect(putMutate).toHaveBeenCalledWith(
      '/relations/overview-scope',
      expect.objectContaining({ max_items: 999 })
    );
    expect(setData).toHaveBeenCalledWith(expect.objectContaining({ max_items: 25 }));
  });

  it('reports a failed write instead of pretending the scope applies', async () => {
    // The caller still opens the chat, but on the STORED scope — so it must
    // be able to tell the two apart.
    const setData = vi.fn();
    useApiQuery.mockReturnValue({
      data: undefined,
      loading: false,
      error: null,
      refetch,
      setData,
    });
    putMutate.mockResolvedValueOnce(undefined);

    const { result } = renderHook(() => useOverviewScope());
    let ok: boolean | undefined;
    await act(async () => {
      ok = await result.current.save({
        sections: [],
        directions: [],
        roles: [],
        max_items: 5,
      });
    });

    expect(ok).toBe(false);
    expect(setData).not.toHaveBeenCalled();
  });
});

describe('useRelationMerge', () => {
  it('sends both sides — the service owns the folding, not the caller', async () => {
    const { result } = renderHook(() => useRelationMerge());

    let verdict: { ok: boolean } | undefined;
    await act(async () => {
      verdict = await result.current.merge('0612345678', 'Alice Vernier');
    });

    expect(postMutate).toHaveBeenCalledWith('/relations/merges', {
      source: '0612345678',
      target: 'Alice Vernier',
    });
    expect(verdict).toEqual({ ok: true });
  });

  it('turns a refused merge into a verdict instead of throwing', async () => {
    // The panel renders an error from this boolean. If the rejection escaped
    // instead, it would cross the whole card and land on the error boundary —
    // the user would lose the page rather than read one sentence.
    postMutate.mockRejectedValueOnce(new Error('400'));
    const { result } = renderHook(() => useRelationMerge());

    let verdict: { ok: boolean } | undefined;
    await act(async () => {
      verdict = await result.current.merge('Alice', 'Alice');
    });

    expect(verdict).toEqual({ ok: false });
  });

  it('escapes the name it undoes — a relationship is called anything', async () => {
    // A merged-away spelling can be a raw number, but also "Marie / bureau"
    // or "R&D". Unescaped, the slash alone would address another route.
    const { result } = renderHook(() => useRelationMerge());

    await act(async () => {
      await result.current.split('Marie / R&D');
    });

    expect(delMutate).toHaveBeenCalledWith('/relations/merges/Marie%20%2F%20R%26D');
  });

  it('turns a refused undo into a verdict too', async () => {
    delMutate.mockRejectedValueOnce(new Error('500'));
    const { result } = renderHook(() => useRelationMerge());

    let verdict: { ok: boolean } | undefined;
    await act(async () => {
      verdict = await result.current.split('Papa');
    });

    expect(verdict).toEqual({ ok: false });
  });
});
