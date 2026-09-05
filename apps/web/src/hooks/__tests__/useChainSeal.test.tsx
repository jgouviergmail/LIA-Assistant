/**
 * useChainSeal — a status is not a verdict (ADR-263, lot 5).
 *
 * The hook's whole job is to keep those two claims apart: one is fetched on
 * mount and asserts nothing, the other runs only when asked and is the only
 * one allowed to say « intact ». The oracles below are what would break if
 * someone merged them for convenience.
 */

import { describe, expect, it, vi, beforeEach } from 'vitest';
import { act, renderHook, waitFor } from '@testing-library/react';

import { useChainSeal } from '@/hooks/useChainSeal';

const get = vi.fn();
vi.mock('@/lib/api-client', () => ({
  default: { get: (...args: unknown[]) => get(...args) },
}));

const apiQuery = vi.fn();
vi.mock('@/hooks/useApiQuery', () => ({
  useApiQuery: (...args: unknown[]) => apiQuery(...args),
}));

vi.mock('@/lib/logger', () => ({
  logger: { error: vi.fn(), warn: vi.fn(), info: vi.fn(), debug: vi.fn() },
}));

const SEAL = {
  sealing_enabled: true,
  entries: 12,
  sealed_until: '2026-09-04T18:00:00Z',
  pending: 2,
};

const VERDICT = {
  ok: true,
  entries: 12,
  sealed_until: '2026-09-04T18:00:00Z',
  pending: 2,
  payloads_checked: 11,
  payloads_skipped: 0,
  head_hash: 'b'.repeat(64),
  broken_at_seq: null,
  reason: null,
};

beforeEach(() => {
  get.mockReset();
  apiQuery.mockReset();
  apiQuery.mockReturnValue({ data: SEAL, loading: false, error: null, refetch: vi.fn() });
});

describe('useChainSeal', () => {
  it('fetches the STATUS on mount and nothing else', () => {
    const { result } = renderHook(() => useChainSeal());

    expect(apiQuery.mock.calls[0][0]).toBe('/effects/chain/status');
    expect(get).not.toHaveBeenCalled();
    expect(result.current.seal).toEqual(SEAL);
    expect(result.current.verdict).toBeUndefined();
  });

  it('walks the chain only when the reader asks', async () => {
    get.mockResolvedValue(VERDICT);
    const { result } = renderHook(() => useChainSeal());

    await act(async () => {
      await result.current.verify();
    });

    expect(get).toHaveBeenCalledWith('/effects/chain/verify');
    expect(result.current.verdict).toEqual(VERDICT);
  });

  it('CLEARS the previous verdict when a later check fails', async () => {
    get.mockResolvedValueOnce(VERDICT);
    const { result } = renderHook(() => useChainSeal());
    await act(async () => {
      await result.current.verify();
    });
    expect(result.current.verdict).toEqual(VERDICT);

    get.mockRejectedValueOnce(new Error('boom'));
    await act(async () => {
      await result.current.verify();
    });

    expect(result.current.verdict).toBeUndefined();
    expect(result.current.error).toBeInstanceOf(Error);
  });

  it('stops reporting a busy check once it settles', async () => {
    get.mockRejectedValue(new Error('boom'));
    const { result } = renderHook(() => useChainSeal());

    await act(async () => {
      await result.current.verify();
    });

    await waitFor(() => expect(result.current.verifying).toBe(false));
  });

  it('surfaces a status failure as its own error', () => {
    const failure = new Error('status down');
    apiQuery.mockReturnValue({ data: null, loading: false, error: failure, refetch: vi.fn() });

    const { result } = renderHook(() => useChainSeal());

    expect(result.current.seal).toBeUndefined();
    expect(result.current.error).toBe(failure);
  });
});
