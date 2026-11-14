/**
 * The summary hook: one read of the whole board's figures, taken again when
 * the board says they may have moved — and never while nobody is looking.
 */
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { renderHook, waitFor } from '@testing-library/react';

import { useWorkboardSummary } from '@/hooks/useWorkboardSummary';
import type { BoardSummary } from '@/types/workboard';

const client = vi.hoisted(() => ({ get: vi.fn() }));
vi.mock('@/lib/api-client', async importOriginal => ({
  ...(await importOriginal<typeof import('@/lib/api-client')>()),
  apiClient: client,
  default: client,
}));
vi.mock('@/hooks/useAuth', () => ({ useAuth: () => ({ user: { id: 'me' } }) }));

function figures(total: number): Partial<BoardSummary> {
  return { total, counts_by_status: { todo: total } };
}

beforeEach(() => {
  vi.clearAllMocks();
});

describe('useWorkboardSummary', () => {
  it('reads nothing while it is not enabled', async () => {
    client.get.mockResolvedValue(figures(1));
    const hook = renderHook(() => useWorkboardSummary(false, 'a'));
    await Promise.resolve();

    expect(client.get).not.toHaveBeenCalled();
    expect(hook.result.current.summary).toBeUndefined();
  });

  it('reads once, then again when the stamp changes — keeping what is on screen meanwhile', async () => {
    client.get.mockResolvedValueOnce(figures(3));
    const hook = renderHook(({ stamp }) => useWorkboardSummary(true, stamp), {
      initialProps: { stamp: 'a' },
    });
    await waitFor(() => expect(hook.result.current.summary?.total).toBe(3));
    expect(client.get).toHaveBeenCalledTimes(1);
    expect(client.get.mock.calls[0]?.[0]).toBe('/workboard/summary');

    // Same stamp: a re-render is no reason to read.
    hook.rerender({ stamp: 'a' });
    expect(client.get).toHaveBeenCalledTimes(1);

    let answer: (value: Partial<BoardSummary>) => void = () => {};
    client.get.mockReturnValueOnce(
      new Promise<Partial<BoardSummary>>(resolve => {
        answer = resolve;
      })
    );
    hook.rerender({ stamp: 'b' });
    await waitFor(() => expect(client.get).toHaveBeenCalledTimes(2));
    // A refresh is not a first load: the figures stay until the answer lands.
    expect(hook.result.current.summary?.total).toBe(3);
    answer(figures(4));
    await waitFor(() => expect(hook.result.current.summary?.total).toBe(4));
  });
});
