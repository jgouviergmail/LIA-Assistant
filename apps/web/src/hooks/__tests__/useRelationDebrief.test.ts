/**
 * useRelationDebrief — when a build is bought, and when it is not.
 *
 * The GET never builds, so it is safe on every mount. The POST costs an LLM
 * call, so three properties are asserted on the CALL COUNT rather than on the
 * rendered state:
 *
 * - it waits for the provider sections to settle, or it races them and pays
 *   the external quota twice for one card;
 * - it fires ONCE per person, whatever re-renders happen after;
 * - it never fires on a FAILED debrief, which would turn a server-side
 *   cooldown into a client-side loop.
 */

import { act, renderHook, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

const { useApiQuery } = vi.hoisted(() => ({ useApiQuery: vi.fn() }));
vi.mock('@/hooks/useApiQuery', () => ({ useApiQuery }));

const { apiPost } = vi.hoisted(() => ({ apiPost: vi.fn() }));
vi.mock('@/lib/api-client', () => ({
  apiClient: { get: vi.fn(), post: apiPost },
  ApiError: class ApiError extends Error {},
}));

vi.mock('@/hooks/useApiMutation', () => ({
  useApiMutation: () => ({ mutate: vi.fn(), loading: false }),
}));

import { useRelationDebrief, type RelationDebrief } from '../useRelations';

function debrief(over: Partial<RelationDebrief> = {}): RelationDebrief {
  return {
    status: 'ready',
    person: 'Gérard Dupont',
    body: {
      headline: 'h',
      where_we_stand: 'w',
      open_points: [],
      suggested_next_step: null,
      notable_facts: [],
    },
    generated_at: '2026-09-07T06:30:00Z',
    generated_for: '2026-09-07',
    sections_used: [],
    unavailable: [],
    can_rebuild: true,
    ...over,
  };
}

const setData = vi.fn();

function mockRead(data: RelationDebrief | undefined, loading = false) {
  useApiQuery.mockReturnValue({ data, loading, error: null, refetch: vi.fn(), setData });
}

/**
 * Mount the hook the way `useApiQuery` really behaves: loading TRUE on the
 * first render (its initial state is `useState(enabled)`), then the answer.
 *
 * A harness that hands back a settled read on the very first render cannot
 * reproduce the state the hook actually meets, and a guard that depends on the
 * load CYCLE would look broken against it.
 */
function mountThenSettle(
  data: RelationDebrief | undefined,
  options: { enabled?: boolean; providerReady?: boolean } = {}
) {
  const { enabled = true, providerReady = true } = options;
  mockRead(undefined, true);
  const utils = renderHook(() =>
    useRelationDebrief('Gérard Dupont', { enabled, providerReady })
  );
  mockRead(data);
  utils.rerender();
  return utils;
}

beforeEach(() => {
  vi.clearAllMocks();
  apiPost.mockResolvedValue(debrief());
});

describe('useRelationDebrief', () => {
  it('reads without building', async () => {
    mockRead(debrief());
    renderHook(() =>
      useRelationDebrief('Gérard Dupont', { enabled: true, providerReady: true })
    );

    await waitFor(() => expect(useApiQuery).toHaveBeenCalled());
    expect(apiPost).not.toHaveBeenCalled();
  });

  it('builds once when nothing stands yet and the provider half has settled', async () => {
    mountThenSettle(debrief({ status: 'absent', body: null }));

    await waitFor(() => expect(apiPost).toHaveBeenCalledOnce());
    expect(apiPost).toHaveBeenCalledWith('/relations/G%C3%A9rard%20Dupont/debrief');
  });

  it('waits for the provider sections rather than racing their caches', async () => {
    mockRead(undefined, true);
    const { rerender } = renderHook(
      ({ ready }) =>
        useRelationDebrief('Gérard Dupont', { enabled: true, providerReady: ready }),
      { initialProps: { ready: false } }
    );
    mockRead(debrief({ status: 'absent', body: null }));
    rerender({ ready: false });

    expect(apiPost).not.toHaveBeenCalled();
    rerender({ ready: true });
    await waitFor(() => expect(apiPost).toHaveBeenCalledOnce());
  });

  it('never buys a second call for the same person', async () => {
    const { rerender } = mountThenSettle(debrief({ status: 'absent', body: null }));

    await waitFor(() => expect(apiPost).toHaveBeenCalledOnce());
    rerender();
    rerender();
    expect(apiPost).toHaveBeenCalledOnce();
  });

  it('never retries a FAILED debrief on sight — that is a cooldown, not a loop', async () => {
    mountThenSettle(debrief({ status: 'failed' }));

    await waitFor(() => expect(useApiQuery).toHaveBeenCalled());
    expect(apiPost).not.toHaveBeenCalled();
  });

  it('builds nothing while the account has the feature off', async () => {
    mountThenSettle(debrief({ status: 'absent', body: null }), { enabled: false });

    await waitFor(() => expect(useApiQuery).toHaveBeenCalled());
    expect(apiPost).not.toHaveBeenCalled();
  });

  it('never decides on the PREVIOUS person answer while the next one loads', async () => {
    // `useApiQuery` keeps the previous data through a refetch: buying a build
    // for one relationship from another one status is the same class of
    // mistake the panel guards against by staging on `loading`.
    mockRead(debrief({ status: 'absent', body: null }), true);
    renderHook(() =>
      useRelationDebrief('Gérard Dupont', { enabled: true, providerReady: true })
    );

    await waitFor(() => expect(useApiQuery).toHaveBeenCalled());
    expect(apiPost).not.toHaveBeenCalled();
  });

  it('waits for the read of the NEW person to actually run', async () => {
    // The timing fact this guards: `useApiQuery` raises `loading` inside its
    // own effect, so on the render where the name changes BOTH `loading` and
    // `data` still belong to the previous person. Deciding there buys a build
    // from somebody else's status — and before the provider caches refill.
    mockRead(debrief({ status: 'ready' }));
    const { rerender } = renderHook(
      ({ person }) => useRelationDebrief(person, { enabled: true, providerReady: true }),
      { initialProps: { person: 'Alice Vernier' } }
    );
    await waitFor(() => expect(useApiQuery).toHaveBeenCalled());
    expect(apiPost).not.toHaveBeenCalled();

    // The stale frame: new name, previous answer, previous (false) loading.
    mockRead(debrief({ status: 'absent', body: null }));
    rerender({ person: 'Gérard Dupont' });
    expect(apiPost).not.toHaveBeenCalled();

    // The query for the new person actually runs, then lands.
    mockRead(undefined, true);
    rerender({ person: 'Gérard Dupont' });
    mockRead(debrief({ status: 'absent', body: null }));
    rerender({ person: 'Gérard Dupont' });
    await waitFor(() => expect(apiPost).toHaveBeenCalledOnce());
    expect(apiPost).toHaveBeenCalledWith('/relations/G%C3%A9rard%20Dupont/debrief');
  });

  it('asks nothing at all with no relationship selected', () => {
    mockRead(undefined);
    renderHook(() => useRelationDebrief(null, { enabled: true, providerReady: true }));

    expect(useApiQuery).toHaveBeenCalledWith('', expect.objectContaining({ enabled: false }));
    expect(apiPost).not.toHaveBeenCalled();
  });

  it('forces a rebuild when the reader asks', async () => {
    mockRead(debrief());
    const { result } = renderHook(() =>
      useRelationDebrief('Gérard Dupont', { enabled: true, providerReady: true })
    );

    await act(async () => {
      await result.current.rebuild();
    });
    expect(apiPost).toHaveBeenCalledWith('/relations/G%C3%A9rard%20Dupont/debrief?force=true');
  });

  it('leaves the current answer standing when a build fails', async () => {
    mockRead(debrief());
    apiPost.mockRejectedValue(new Error('provider down'));
    const { result } = renderHook(() =>
      useRelationDebrief('Gérard Dupont', { enabled: true, providerReady: true })
    );

    await act(async () => {
      await result.current.rebuild();
    });
    // Nothing was written over the debrief the reader can still use.
    expect(setData).not.toHaveBeenCalled();
    expect(result.current.debrief).not.toBeNull();
  });

  it('reports a build somebody else owns as in flight', () => {
    mockRead(debrief({ status: 'building', body: null }));
    const { result } = renderHook(() =>
      useRelationDebrief('Gérard Dupont', { enabled: true, providerReady: true })
    );

    expect(result.current.building).toBe(true);
  });

  it('stages the first read only, never a rebuild', () => {
    mockRead(undefined, true);
    const { result } = renderHook(() =>
      useRelationDebrief('Gérard Dupont', { enabled: true, providerReady: true })
    );
    expect(result.current.loading).toBe(true);

    mockRead(debrief(), true);
    const { result: refreshing } = renderHook(() =>
      useRelationDebrief('Gérard Dupont', { enabled: true, providerReady: true })
    );
    expect(refreshing.current.loading).toBe(false);
  });
});
