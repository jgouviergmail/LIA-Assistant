import { act, renderHook } from '@testing-library/react';
import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import apiClient from '@/lib/api-client';
import { useCompanionEnvironmentStore as store } from '@/stores/companionEnvironmentStore';
import { useCompanionEnvironment } from '../useCompanionEnvironment';

vi.mock('@/lib/api-client', () => ({ default: { get: vi.fn() } }));
const result = { timezone: 'Europe/Paris', weather: null };
beforeEach(() => {
  vi.useFakeTimers();
  vi.clearAllMocks();
  store.getState().reset();
});
afterEach(() => {
  vi.useRealTimers();
  vi.restoreAllMocks();
});
const flush = async () => {
  await act(async () => {
    await Promise.resolve();
  });
};

it('makes no request for a disabled/landing/minimized face', () => {
  const view = renderHook(() => useCompanionEnvironment(false));
  expect(apiClient.get).not.toHaveBeenCalled();
  view.unmount();
});

it('reads the bounded endpoint and forgets the previous account on unmount', async () => {
  vi.mocked(apiClient.get).mockResolvedValue(result);
  const view = renderHook(() => useCompanionEnvironment(true));
  await flush();
  expect(apiClient.get).toHaveBeenCalledWith(
    '/briefing/companion-context',
    expect.objectContaining({ signal: expect.any(AbortSignal) })
  );
  expect(store.getState().environment).toEqual(result);
  view.unmount();
  expect(store.getState().environment).toBeNull();
  expect(vi.getTimerCount()).toBe(0);
});

it('aborts and ignores a result that arrives after unmount', async () => {
  let resolve: (value: unknown) => void = () => {};
  vi.mocked(apiClient.get).mockReturnValue(
    new Promise(done => {
      resolve = done;
    })
  );
  const view = renderHook(() => useCompanionEnvironment(true));
  const signal = vi.mocked(apiClient.get).mock.calls[0][1]?.signal;
  view.unmount();
  expect(signal?.aborted).toBe(true);
  await act(async () => resolve(result));
  expect(store.getState().environment).toBeNull();
});

it('suspends in a hidden tab and does not refetch on repeated focus inside the interval', async () => {
  const hidden = vi.spyOn(document, 'hidden', 'get').mockReturnValue(true);
  vi.mocked(apiClient.get).mockResolvedValue(result);
  const view = renderHook(() => useCompanionEnvironment(true));
  expect(apiClient.get).not.toHaveBeenCalled();
  hidden.mockReturnValue(false);
  act(() => document.dispatchEvent(new Event('visibilitychange')));
  await flush();
  expect(apiClient.get).toHaveBeenCalledTimes(1);
  hidden.mockReturnValue(true);
  act(() => document.dispatchEvent(new Event('visibilitychange')));
  expect(vi.getTimerCount()).toBe(0);
  hidden.mockReturnValue(false);
  act(() => document.dispatchEvent(new Event('visibilitychange')));
  await flush();
  expect(apiClient.get).toHaveBeenCalledTimes(1);
  await act(async () => vi.advanceTimersByTime(15 * 60_000));
  expect(apiClient.get).toHaveBeenCalledTimes(2);
  view.unmount();
});

it('stays neutral on malformed payload or network failure, then can recover', async () => {
  vi.mocked(apiClient.get)
    .mockResolvedValueOnce({ timezone: 'bad' })
    .mockRejectedValueOnce(new Error('offline'))
    .mockResolvedValue(result);
  const view = renderHook(() => useCompanionEnvironment(true));
  await flush();
  expect(store.getState().environment).toBeNull();
  await act(async () => vi.advanceTimersByTime(15 * 60_000));
  expect(store.getState().environment).toBeNull();
  await act(async () => vi.advanceTimersByTime(15 * 60_000));
  expect(store.getState().environment).toEqual(result);
  view.unmount();
});
