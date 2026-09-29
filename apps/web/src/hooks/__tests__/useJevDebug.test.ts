import { act, renderHook } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import apiClient from '@/lib/api-client';
import { useJevDebug } from '../useJevDebug';

beforeEach(() => {
  vi.restoreAllMocks();
  vi.useFakeTimers();
});
afterEach(() => {
  vi.useRealTimers();
  vi.restoreAllMocks();
});

describe('temporary JEV feed polling', () => {
  it('polls only a visible idle view, aborts pending requests on unmount, and stops its timer', async () => {
    const visible = vi.spyOn(document, 'visibilityState', 'get').mockReturnValue('visible');
    const get = vi
      .spyOn(apiClient, 'get')
      .mockResolvedValue({ calls: [], limit: 30, retention_seconds: 3600 });
    const { result, unmount } = renderHook(() => useJevDebug());
    await act(async () => {
      await vi.advanceTimersByTimeAsync(0);
    });
    expect(get).toHaveBeenCalledTimes(1);
    expect(result.current.data?.calls).toEqual([]);
    await act(async () => {
      await vi.advanceTimersByTimeAsync(5000);
    });
    expect(get).toHaveBeenCalledTimes(2);
    visible.mockReturnValue('hidden');
    await act(async () => {
      await vi.advanceTimersByTimeAsync(10000);
    });
    expect(get).toHaveBeenCalledTimes(2);
    visible.mockReturnValue('visible');
    get.mockReturnValue(new Promise(() => {}));
    await act(async () => {
      await vi.advanceTimersByTimeAsync(5000);
    });
    expect(get).toHaveBeenCalledTimes(3);
    await act(async () => {
      await vi.advanceTimersByTimeAsync(10000);
    });
    expect(get).toHaveBeenCalledTimes(3);
    const signal = get.mock.calls[2][1]?.signal;
    unmount();
    expect(signal?.aborted).toBe(true);
    await act(async () => {
      await vi.advanceTimersByTimeAsync(10000);
    });
    expect(get).toHaveBeenCalledTimes(3);
  });
});
