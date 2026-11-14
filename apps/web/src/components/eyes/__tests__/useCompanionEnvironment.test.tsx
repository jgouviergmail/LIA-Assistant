import { act, renderHook } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import apiClient from '@/lib/api-client';
import { useCompanionEnvironmentStore as store } from '@/stores/companionEnvironmentStore';
import { useCompanionEnvironment } from '../useCompanionEnvironment';
import { liveActingContext } from '../rig/live-context';

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

it('retires stale combined evidence on its deadline with the same timer and no extra request', async () => {
  const now = Date.parse('2026-09-21T12:00:00Z');
  vi.setSystemTime(now);
  const observed = {
    timezone: 'Pacific/Auckland',
    weather: {
      temperature_c: 5,
      condition_code: 'Rain',
      wind_speed_kmh: 45,
      observed_at: new Date(now - 1000).toISOString(),
      expires_at: new Date(now + 1000).toISOString(),
    },
  };
  vi.mocked(apiClient.get).mockResolvedValue(observed);
  const view = renderHook(() => useCompanionEnvironment(true));
  await flush();
  expect(liveActingContext(Date.now())).toMatchObject({
    weatherFlags: ['rain', 'wind', 'cold'],
    weather: 'rain',
    dayPhase: 'night',
  });
  expect(vi.getTimerCount()).toBe(1);
  await act(async () => vi.advanceTimersByTime(999));
  expect(store.getState().environment?.weather).toEqual(observed.weather);
  await act(async () => vi.advanceTimersByTime(1));
  expect(store.getState().environment).toEqual({ timezone: observed.timezone, weather: null });
  expect(liveActingContext(Date.now())).toMatchObject({
    weatherFlags: [],
    weather: null,
    dayPhase: 'night',
  });
  expect(apiClient.get).toHaveBeenCalledTimes(1);
  expect(vi.getTimerCount()).toBe(1);
  expect(observed.weather.condition_code).toBe('Rain');
  await act(async () => vi.advanceTimersByTime(15 * 60_000 - 1000));
  expect(apiClient.get).toHaveBeenCalledTimes(2);
  view.unmount();
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

describe('a newer weather LIA read reaches the face at once (ADR-294, 2026-11-13)', () => {
  const NOW = Date.parse('2026-09-21T12:00:00Z');
  const reading = (condition: string, minutesAgo: number) => ({
    timezone: 'UTC',
    weather: {
      temperature_c: 12,
      condition_code: condition,
      wind_speed_kmh: 5,
      observed_at: new Date(NOW - minutesAgo * 60_000).toISOString(),
      expires_at: new Date(NOW + 40 * 60_000).toISOString(),
    },
  });

  it('reads it when told, not at the next quarter hour', async () => {
    vi.setSystemTime(NOW);
    vi.mocked(apiClient.get)
      .mockResolvedValueOnce(reading('Clear', 10))
      .mockResolvedValueOnce(reading('Rain', 0));
    const view = renderHook(() => useCompanionEnvironment(true));
    await flush();
    expect(store.getState().environment?.weather?.condition_code).toBe('Clear');

    await act(async () => store.getState().requestRefresh());
    await flush();

    expect(apiClient.get).toHaveBeenCalledTimes(2);
    expect(store.getState().environment?.weather?.condition_code).toBe('Rain');
    view.unmount();
  });

  it('reads once more after a read that was already on its way', async () => {
    // That read may have left before the newer observation was kept.
    let answer!: (value: unknown) => void;
    vi.mocked(apiClient.get)
      .mockImplementationOnce(() => new Promise(resolve => void (answer = resolve)))
      .mockResolvedValue(result);
    const view = renderHook(() => useCompanionEnvironment(true));
    await flush();

    await act(async () => store.getState().requestRefresh());
    expect(apiClient.get).toHaveBeenCalledTimes(1);
    await act(async () => answer(result));
    await flush();

    expect(apiClient.get).toHaveBeenCalledTimes(2);
    view.unmount();
  });

  it('keeps a request made out of sight for the moment the page is looked at', async () => {
    vi.mocked(apiClient.get).mockResolvedValue(result);
    const hidden = vi.spyOn(document, 'hidden', 'get').mockReturnValue(false);
    const view = renderHook(() => useCompanionEnvironment(true));
    await flush();
    hidden.mockReturnValue(true);
    act(() => document.dispatchEvent(new Event('visibilitychange')));

    await act(async () => store.getState().requestRefresh());
    expect(apiClient.get).toHaveBeenCalledTimes(1);
    hidden.mockReturnValue(false);
    act(() => document.dispatchEvent(new Event('visibilitychange')));
    await flush();

    // Inside the quarter hour: only the request makes it read again.
    expect(apiClient.get).toHaveBeenCalledTimes(2);
    view.unmount();
  });

  it('serves a request the hidden page cut short with one read on return, not two', async () => {
    // The read on its way is abandoned when the page hides; the read the page
    // makes on return is newer than the request, so nothing is left to read again.
    vi.mocked(apiClient.get)
      .mockImplementationOnce(() => new Promise(() => undefined))
      .mockResolvedValue(result);
    const hidden = vi.spyOn(document, 'hidden', 'get').mockReturnValue(false);
    const view = renderHook(() => useCompanionEnvironment(true));
    await flush();

    await act(async () => store.getState().requestRefresh());
    hidden.mockReturnValue(true);
    act(() => document.dispatchEvent(new Event('visibilitychange')));
    hidden.mockReturnValue(false);
    act(() => document.dispatchEvent(new Event('visibilitychange')));
    await flush();
    await flush();

    expect(apiClient.get).toHaveBeenCalledTimes(2);
    view.unmount();
  });

  it('lets go of the store when it unmounts', async () => {
    vi.mocked(apiClient.get).mockResolvedValue(result);
    const subscribe = store.subscribe;
    const released = vi.fn();
    vi.spyOn(store, 'subscribe').mockImplementation(listener => {
      const unsubscribe = subscribe(listener);
      return () => {
        released();
        unsubscribe();
      };
    });
    const view = renderHook(() => useCompanionEnvironment(true));
    await flush();

    view.unmount();

    expect(released).toHaveBeenCalledTimes(1);
  });

  it('asks nothing of an account that shows no face', async () => {
    const view = renderHook(() => useCompanionEnvironment(false));

    await act(async () => store.getState().requestRefresh());

    expect(apiClient.get).not.toHaveBeenCalled();
    view.unmount();
  });
});
