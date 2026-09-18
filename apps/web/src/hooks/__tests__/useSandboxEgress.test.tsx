/**
 * useSandboxEgress (ADR-298) — the two reads, the exact total, and the
 * optimistic edits that roll back when the server refuses.
 */

import { renderHook, waitFor } from '@testing-library/react';
import { act } from 'react';
import { describe, expect, it, vi, beforeEach } from 'vitest';

import { ApiError } from '@/lib/api-client';

const queries = vi.hoisted(() => ({
  byPath: {} as Record<string, { data: unknown; loading: boolean; error: Error | null }>,
  paths: [] as string[],
  refetch: vi.fn(),
}));
const mutation = vi.hoisted(() => ({
  calls: [] as Array<{ method: string; endpoint: string; body: unknown }>,
  fail: false,
}));

vi.mock('@/hooks/useApiQuery', () => ({
  useApiQuery: (path: string) => {
    queries.paths.push(path);
    const q = queries.byPath[path] ?? { data: null, loading: false, error: null };
    return { ...q, refetch: queries.refetch };
  },
}));
vi.mock('@/hooks/useApiMutation', () => ({
  useApiMutation: ({ method }: { method: string }) => ({
    mutate: async (endpoint: string, body?: unknown) => {
      mutation.calls.push({ method, endpoint, body });
      if (mutation.fail) throw new ApiError('refused', 500);
      return undefined;
    },
    loading: false,
    error: null,
    data: null,
  }),
}));

import { GRANTS_PATH, REACHABLE_PATH, useSandboxEgress } from '@/hooks/useSandboxEgress';

function seed(total = 2) {
  queries.byPath[REACHABLE_PATH] = {
    data: {
      items: [{ host: 'api.search.brave.com', status: 'connector', connector: 'brave_search' }],
      ask_enabled: true,
    },
    loading: false,
    error: null,
  };
  queries.byPath[GRANTS_PATH] = {
    data: {
      items: [
        {
          id: 'g-1',
          host: 'a.example',
          share_turn_data: true,
          created_at: '2026-09-18T08:00:00Z',
          last_used_at: null,
        },
        {
          id: 'g-2',
          host: 'b.example',
          share_turn_data: false,
          created_at: '2026-09-18T08:00:00Z',
          last_used_at: null,
        },
      ],
      total,
      limit: 50,
      offset: 0,
      max_limit: 50,
      max_per_user: 50,
    },
    loading: false,
    error: null,
  };
}

beforeEach(() => {
  vi.clearAllMocks();
  queries.byPath = {};
  queries.paths = [];
  mutation.calls = [];
  mutation.fail = false;
});

describe('useSandboxEgress', () => {
  it('reads the two surfaces and hands the exact total, never the page length', () => {
    seed(7);
    const { result } = renderHook(() => useSandboxEgress());
    expect(queries.paths).toEqual(expect.arrayContaining([REACHABLE_PATH, GRANTS_PATH]));
    expect(result.current.reachable).toHaveLength(1);
    expect(result.current.askEnabled).toBe(true);
    expect(result.current.grants).toHaveLength(2);
    expect(result.current.total).toBe(7);
    expect(result.current.maxPerUser).toBe(50);
  });

  it('is unavailable on a 404 and in error on anything else', () => {
    seed();
    queries.byPath[REACHABLE_PATH].error = new ApiError('gone', 404);
    let hook = renderHook(() => useSandboxEgress());
    expect(hook.result.current.unavailable).toBe(true);
    expect(hook.result.current.loadError).toBe(false);

    queries.byPath[REACHABLE_PATH].error = new Error('network');
    hook = renderHook(() => useSandboxEgress());
    expect(hook.result.current.unavailable).toBe(false);
    expect(hook.result.current.loadError).toBe(true);
  });

  it('changes a scope optimistically and keeps it once the server accepts', async () => {
    seed();
    const { result } = renderHook(() => useSandboxEgress());
    let ok = false;
    await act(async () => {
      ok = await result.current.setScope('g-1', false);
    });
    expect(ok).toBe(true);
    expect(mutation.calls).toEqual([
      { method: 'PATCH', endpoint: '/sandbox/egress-grants/g-1', body: { share_turn_data: false } },
    ]);
    expect(result.current.grants.find(g => g.id === 'g-1')?.share_turn_data).toBe(false);
  });

  it('rolls a refused scope change back', async () => {
    seed();
    mutation.fail = true;
    const { result } = renderHook(() => useSandboxEgress());
    let ok = true;
    await act(async () => {
      ok = await result.current.setScope('g-1', false);
    });
    expect(ok).toBe(false);
    await waitFor(() =>
      expect(result.current.grants.find(g => g.id === 'g-1')?.share_turn_data).toBe(true)
    );
  });

  it('revokes optimistically, lowering the exact total by one', async () => {
    seed(2);
    const { result } = renderHook(() => useSandboxEgress());
    await act(async () => {
      await result.current.revoke('g-2');
    });
    expect(mutation.calls).toEqual([
      { method: 'DELETE', endpoint: '/sandbox/egress-grants/g-2', body: undefined },
    ]);
    expect(result.current.grants.map(g => g.id)).toEqual(['g-1']);
    expect(result.current.total).toBe(1);
  });

  it('puts a grant back when the revoke is refused', async () => {
    seed(2);
    mutation.fail = true;
    const { result } = renderHook(() => useSandboxEgress());
    let ok = true;
    await act(async () => {
      ok = await result.current.revoke('g-2');
    });
    expect(ok).toBe(false);
    await waitFor(() => expect(result.current.grants).toHaveLength(2));
    expect(result.current.total).toBe(2);
  });

  it('refetch clears the optimistic overrides and asks both surfaces again', async () => {
    seed();
    const { result } = renderHook(() => useSandboxEgress());
    await act(async () => {
      await result.current.revoke('g-2');
    });
    act(() => result.current.refetch());
    expect(queries.refetch).toHaveBeenCalledTimes(2);
    await waitFor(() => expect(result.current.grants).toHaveLength(2));
  });
});

describe('the pure helpers', () => {
  const rows = [
    { id: 'a', host: 'a.example', share_turn_data: true, created_at: 't', last_used_at: null },
    { id: 'b', host: 'b.example', share_turn_data: false, created_at: 't', last_used_at: null },
  ];

  it('applyOverrides drops revoked rows and rewrites edited scopes only', async () => {
    const { applyOverrides } = await import('@/hooks/useSandboxEgress');
    const out = applyOverrides(rows, new Set(['b']), { a: false });
    expect(out).toEqual([{ ...rows[0], share_turn_data: false }]);
  });

  it('exactTotal starts from the server total and subtracts only revokes on the page', async () => {
    const { exactTotal } = await import('@/hooks/useSandboxEgress');
    const page = { items: rows, total: 9, limit: 50, offset: 0, max_limit: 50, max_per_user: 50 };
    expect(exactTotal(page, new Set(['b', 'zz']))).toBe(8);
    expect(exactTotal(null, new Set(['b']))).toBe(0);
  });

  it('readFailure ranks a 404 above a transient failure', async () => {
    const { readFailure } = await import('@/hooks/useSandboxEgress');
    expect(readFailure([null, null])).toBeNull();
    expect(readFailure([new Error('x'), null])).toBe('error');
    expect(readFailure([new Error('x'), new ApiError('gone', 404)])).toBe('unavailable');
  });
});
