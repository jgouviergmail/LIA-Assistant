import { act, cleanup, render, renderHook } from '@testing-library/react';
import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import apiClient from '@/lib/api-client';
import { useCompanionEnvironmentStore as store } from '@/stores/companionEnvironmentStore';
import { useEyesSignalsStore as signals } from '@/stores/eyesSignalsStore';
import { usePsycheStore } from '@/stores/psycheStore';
import { installSpiritBrowser } from '@/components/spirit/__tests__/browser';
import { useCompanionEnvironment } from '../useCompanionEnvironment';
import { ExpressiveEyes } from '../ExpressiveEyes';
import { liveActingContext } from '../rig/live-context';
import { activeFrameSubscribers } from '../rig/scheduler';
import type { EyeExpression } from '../expression-engine';

vi.mock('@/lib/api-client', () => ({ default: { get: vi.fn() } }));

const NOW = Date.parse('2026-09-21T12:00:00Z');
function observation(observedAt = NOW - 1000, expiresAt = NOW + 1000) {
  return {
    timezone: 'Pacific/Auckland',
    weather: {
      temperature_c: 5,
      condition_code: 'Rain',
      wind_speed_kmh: 45,
      observed_at: new Date(observedAt).toISOString(),
      expires_at: new Date(expiresAt).toISOString(),
    },
  };
}

beforeEach(() => {
  installSpiritBrowser(true);
  vi.spyOn(document, 'hidden', 'get').mockReturnValue(false);
  vi.useFakeTimers({
    toFake: ['Date', 'setTimeout', 'clearTimeout', 'requestAnimationFrame', 'cancelAnimationFrame'],
  });
  vi.setSystemTime(NOW);
  vi.clearAllMocks();
  store.getState().reset();
  signals.getState().reset();
  usePsycheStore.getState().reset();
});

afterEach(() => {
  cleanup();
  store.getState().reset();
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
  vi.useRealTimers();
});

async function flush() {
  await act(async () => {
    await Promise.resolve();
  });
}

it('retains evidence during failed refreshes only until its original deadline', async () => {
  const refreshMs = 15 * 60_000;
  vi.mocked(apiClient.get)
    .mockResolvedValueOnce(observation(NOW - 1000, NOW + 2 * refreshMs))
    .mockRejectedValueOnce(new Error('offline'))
    .mockResolvedValueOnce({ timezone: 'invalid' });
  const view = renderHook(() => useCompanionEnvironment(true));
  await flush();
  const cached = store.getState().environment;
  await act(async () => vi.advanceTimersByTime(refreshMs));
  expect(store.getState().environment).toBe(cached);
  expect(liveActingContext(Date.now())).toMatchObject({
    weatherFlags: ['rain', 'wind', 'cold'],
    dayPhase: 'night',
  });
  expect(vi.getTimerCount()).toBe(1);
  await act(async () => vi.advanceTimersByTime(refreshMs));
  expect(store.getState().environment).toEqual({ timezone: 'Pacific/Auckland', weather: null });
  expect(liveActingContext(Date.now())).toMatchObject({ weatherFlags: [], dayPhase: 'night' });
  expect(apiClient.get).toHaveBeenCalledTimes(3);
  view.unmount();
  expect(vi.getTimerCount()).toBe(0);
});

it('signals the actual observation boundary without polling or changing its raw snapshot', async () => {
  vi.mocked(apiClient.get).mockResolvedValue(observation(NOW + 1000, NOW + 2000));
  const view = renderHook(() => useCompanionEnvironment(true));
  await flush();
  const cached = store.getState().environment;
  const delivered: (readonly string[] | undefined)[] = [];
  const unsubscribe = store.subscribe(() =>
    delivered.push(liveActingContext(Date.now()).weatherFlags)
  );
  expect(liveActingContext(Date.now()).weatherFlags).toEqual([]);
  await act(async () => vi.advanceTimersByTime(999));
  expect(delivered).toEqual([]);
  await act(async () => vi.advanceTimersByTime(1));
  expect(delivered).toEqual([['rain', 'wind', 'cold']]);
  expect(store.getState().environment).toBe(cached);
  await act(async () => vi.advanceTimersByTime(1000));
  expect(delivered).toEqual([['rain', 'wind', 'cold'], []]);
  expect(apiClient.get).toHaveBeenCalledTimes(1);
  expect(vi.getTimerCount()).toBe(1);
  unsubscribe();
  view.unmount();
});

it('expires cached evidence while a refresh is still in flight without duplicating the request', async () => {
  const refreshMs = 15 * 60_000;
  let resolveRefresh: (payload: unknown) => void = () => {};
  vi.mocked(apiClient.get)
    .mockResolvedValueOnce(observation(NOW - 1000, NOW + refreshMs + 1000))
    .mockImplementationOnce(
      () =>
        new Promise(resolve => {
          resolveRefresh = resolve;
        })
    );
  const view = renderHook(() => useCompanionEnvironment(true));
  await flush();
  await act(async () => vi.advanceTimersByTime(refreshMs));
  expect(apiClient.get).toHaveBeenCalledTimes(2);
  await act(async () => vi.advanceTimersByTime(1000));
  expect(store.getState().environment).toEqual({ timezone: 'Pacific/Auckland', weather: null });
  expect(apiClient.get).toHaveBeenCalledTimes(2);
  expect(vi.getTimerCount()).toBe(1);
  await act(async () => resolveRefresh({ timezone: 'Pacific/Auckland', weather: null }));
  view.unmount();
  expect(vi.getTimerCount()).toBe(0);
});

function EnvironmentFace({ expression }: { expression: EyeExpression }) {
  useCompanionEnvironment(true);
  return <ExpressiveEyes expression={expression} styleId="cozmo" gaze={null} size="sm" life />;
}

it('propagates cumulative props through the actual native writer across working, sleep and speech', async () => {
  vi.mocked(apiClient.get).mockResolvedValue(observation());
  signals.getState().beginTurn('answer');
  signals.getState().recordActivity(
    {
      version: 1,
      run_id: 'run',
      invocation_id: 'call',
      family: 'reading',
      intent: 'read',
      phase: 'started',
      outcome: null,
    },
    'answer',
    false,
    NOW
  );
  const view = render(<EnvironmentFace expression="neutral" />);
  await flush();
  const host = view.container.querySelector<HTMLElement>('.lia-eyes');
  expect(host).not.toBeNull();
  for (const expression of [
    'neutral',
    'thinking',
    'sleep',
    'speaking',
    'anger',
  ] as const satisfies readonly EyeExpression[]) {
    view.rerender(<EnvironmentFace expression={expression} />);
    act(() => vi.advanceTimersByTime(48));
    expect(host).toHaveAttribute('data-expression', expression);
    const props = host?.dataset.weatherProps?.split(' ') ?? [];
    expect(props).toEqual(expect.arrayContaining(['rain', 'cold', 'wind', 'night']));
    expect(props).toHaveLength(4);
    expect(activeFrameSubscribers()).toBe(0);
  }
  act(() => vi.advanceTimersByTime(NOW + 1032 - Date.now()));
  expect(host?.dataset.weatherProps).toBe('night');
  expect(apiClient.get).toHaveBeenCalledTimes(1);
  expect(activeFrameSubscribers()).toBe(0);
  view.unmount();
  expect(vi.getTimerCount()).toBe(0);
});
