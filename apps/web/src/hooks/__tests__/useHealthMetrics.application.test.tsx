import { act, renderHook, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { publishApplicationResources } from '@/lib/application-resources';

const { get, useAuth } = vi.hoisted(() => ({ get: vi.fn(), useAuth: vi.fn() }));
vi.mock('@/hooks/useAuth', () => ({ useAuth }));
vi.mock('@/lib/api-client', async importOriginal => {
  const original = await importOriginal<typeof import('@/lib/api-client')>();
  return { ...original, default: { get } };
});
import { useHealthMetrics } from '../useHealthMetrics';

const aggregate = {
  period: 'day',
  from_ts: '2026-01-01T00:00:00Z',
  to_ts: '2026-01-02T00:00:00Z',
  points: [],
  averages: { heart_rate_avg: 80, steps_per_day_avg: 1000 },
};
const token = {
  id: 'token-one',
  token_prefix: 'hm_public',
  label: 'Watch',
  created_at: '2026-01-01T00:00:00Z',
  last_used_at: null,
  revoked_at: null,
};
beforeEach(() => {
  vi.resetAllMocks();
  useAuth.mockReturnValue({ user: { id: 'one' } });
  get.mockImplementation((endpoint: string) =>
    Promise.resolve(
      endpoint.startsWith('/health-metrics/aggregate') ? aggregate : { tokens: [token] }
    )
  );
});

describe('health management follows the active account', () => {
  it('refreshes after owned changes and ignores foreign invalidation', async () => {
    const { result } = renderHook(() => useHealthMetrics());
    await waitFor(() => expect(result.current.tokens).toHaveLength(1));
    get.mockClear();
    act(() => publishApplicationResources('foreign', new Set(['health_metrics'])));
    expect(get).not.toHaveBeenCalled();
    get.mockImplementation((endpoint: string) =>
      Promise.resolve(
        endpoint.startsWith('/health-metrics/aggregate')
          ? { ...aggregate, averages: { heart_rate_avg: null, steps_per_day_avg: null } }
          : { tokens: [] }
      )
    );
    act(() => publishApplicationResources('one', new Set(['health_metrics'])));
    await waitFor(() => expect(result.current.aggregate?.averages.heart_rate_avg).toBeNull());
    expect(result.current.tokens).toEqual([]);
  });

  it('re-reads in place, and withdraws old values when the reread fails', async () => {
    const { result } = renderHook(() => useHealthMetrics());
    await waitFor(() => expect(result.current.aggregate?.averages.heart_rate_avg).toBe(80));
    get.mockRejectedValue(new Error('offline'));
    act(() => publishApplicationResources('one', new Set(['health_metrics'])));
    // In place while it re-reads: a refresh is never a visible reload (owner
    // rule 2026-10-21) ...
    expect(result.current.aggregate?.averages.heart_rate_avg).toBe(80);
    // ... but a reread that failed cannot vouch for them: an erasure may be
    // the very change it was reading.
    await waitFor(() => expect(result.current.aggregate).toBeUndefined());
  });

  it('hides the previous owner while the new account reads remain pending', async () => {
    const { result, rerender } = renderHook(() => useHealthMetrics());
    await waitFor(() => expect(result.current.tokens).toHaveLength(1));
    useAuth.mockReturnValue({ user: { id: 'two' } });
    get.mockReturnValue(new Promise(() => {}));
    rerender();
    expect(result.current.aggregate).toBeUndefined();
    expect(result.current.tokens).toEqual([]);
    await waitFor(() => {
      expect(get).toHaveBeenCalledTimes(4);
      expect(result.current.isLoading).toBe(true);
    });
  });
});
