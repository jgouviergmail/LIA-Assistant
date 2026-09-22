import { act, cleanup, renderHook } from '@testing-library/react';
import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import { useEyesBehavior } from '../useEyesBehavior';
import { useCompanionEnvironmentStore as environment } from '@/stores/companionEnvironmentStore';
import { useEyesSignalsStore } from '@/stores/eyesSignalsStore';
import { usePsycheStore } from '@/stores/psycheStore';

beforeEach(() => {
  vi.useFakeTimers();
  vi.setSystemTime(new Date('2026-09-21T12:00:00Z'));
  environment.getState().reset();
  useEyesSignalsStore.getState().reset();
  usePsycheStore.getState().reset();
});
afterEach(() => {
  cleanup();
  environment.getState().reset();
  vi.useRealTimers();
});

it('uses the account clock for attitude as well as light, and reacts to a timezone change', () => {
  environment.getState().setEnvironment({ timezone: 'Pacific/Auckland', weather: null });
  const { result } = renderHook(() =>
    useEyesBehavior({
      chatStatus: 'idle',
      streamPhase: 'answer',
      hitlAwaiting: false,
      enabled: true,
    })
  );
  act(() => vi.advanceTimersByTime(1200));
  expect(result.current.frame.expression).toBe('sleepy');
  act(() => environment.getState().setEnvironment({ timezone: 'UTC', weather: null }));
  act(() => vi.advanceTimersByTime(1200));
  expect(result.current.frame.expression).toBe('neutral');
});

it('never lets night-time atmosphere outrank real processing', () => {
  environment.getState().setEnvironment({ timezone: 'Pacific/Auckland', weather: null });
  const { result } = renderHook(() =>
    useEyesBehavior({
      chatStatus: 'streaming',
      streamPhase: 'progress',
      hitlAwaiting: false,
      enabled: true,
    })
  );
  act(() => vi.advanceTimersByTime(1200));
  expect(result.current.frame.expression).toBe('thinking');
});
