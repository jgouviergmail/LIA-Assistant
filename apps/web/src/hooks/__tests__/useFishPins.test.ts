/**
 * useFishPins — the instance's public Fish Audio voices, ONE list for every
 * voice slot (ADR-345 amendment 2026-10-14): read while wanted, pinned with the
 * administrator's attestation, unpinned, and every act adopts the list the
 * server answered with — never a list the page assembled itself.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { act, renderHook, waitFor } from '@testing-library/react';

const api = vi.hoisted(() => ({ get: vi.fn(), put: vi.fn(), delete: vi.fn() }));
vi.mock('@/lib/api-client', () => ({
  default: api,
  ApiError: class ApiError extends Error {},
  apiEndpointUrl: (path: string) => path,
}));

import { FISH_PINS_ENDPOINT, useFishPins } from '../useFishPins';

const A = 'a'.repeat(32);
const B = 'b'.repeat(32);

describe('useFishPins', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    api.get.mockResolvedValue({ voice_ids: [A], max_pins: 20 });
  });

  it('reads the shared list only while it is wanted', async () => {
    const { result, rerender } = renderHook(({ enabled }) => useFishPins(enabled), {
      initialProps: { enabled: false },
    });
    expect(api.get).not.toHaveBeenCalled();
    expect(result.current.pins).toBeUndefined();

    rerender({ enabled: true });
    await waitFor(() => expect(result.current.pins).toEqual({ voice_ids: [A], max_pins: 20 }));
    expect(api.get).toHaveBeenCalledWith(FISH_PINS_ENDPOINT, expect.anything());
  });

  it('pins with the attestation the page holds and adopts the list the server answers', async () => {
    // Another administrator pinned B meanwhile: the answer says so.
    api.put.mockResolvedValue({ voice_ids: [A, B, 'c'.repeat(32)], max_pins: 20 });
    const { result } = renderHook(() => useFishPins(true));
    await waitFor(() => expect(result.current.pins).toBeDefined());

    await act(() => result.current.pin(B, true));

    expect(api.put).toHaveBeenCalledWith(`${FISH_PINS_ENDPOINT}/${B}`, { attested: true });
    expect(result.current.pins?.voice_ids).toEqual([A, B, 'c'.repeat(32)]);
  });

  it('unpins and adopts the remaining list', async () => {
    api.delete.mockResolvedValue({ voice_ids: [], max_pins: 20 });
    const { result } = renderHook(() => useFishPins(true));
    await waitFor(() => expect(result.current.pins).toBeDefined());

    await act(() => result.current.unpin(A));

    expect(api.delete).toHaveBeenCalledWith(`${FISH_PINS_ENDPOINT}/${A}`);
    expect(result.current.pins?.voice_ids).toEqual([]);
  });

  it('keeps the list it holds when the server refuses an act', async () => {
    api.put.mockRejectedValue(new Error('refused'));
    const { result } = renderHook(() => useFishPins(true));
    await waitFor(() => expect(result.current.pins).toBeDefined());

    await expect(act(() => result.current.pin(B, true))).rejects.toThrow('refused');

    expect(result.current.pins?.voice_ids).toEqual([A]);
  });
});
