import { act, renderHook } from '@testing-library/react';
import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import { useWorldEnvironment } from '../useWorldEnvironment';

const port = vi.hoisted(() => ({ get: vi.fn(), owner: 'owner-a' }));
vi.mock('@/hooks/useAuth', () => ({
  useAuth: () => ({ user: { id: port.owner, is_active: true } }),
}));
vi.mock('@/lib/api-client', async importOriginal => ({
  ...(await importOriginal<typeof import('@/lib/api-client')>()),
  default: { get: port.get },
}));
const serverTime = Date.parse('2026-10-23T12:00:00Z');
function environment(timezone: string, expiresIn = 60_000) {
  return {
    server_time: serverTime / 1000,
    timezone,
    weather: {
      temperature_c: 12,
      condition_code: 'Rain',
      wind_speed_kmh: 4,
      observed_at: new Date(serverTime - 1000).toISOString(),
      expires_at: new Date(serverTime + expiresIn).toISOString(),
    },
  };
}
async function settle() {
  await act(async () => {
    await Promise.resolve();
    await Promise.resolve();
  });
}
beforeEach(() => {
  vi.useFakeTimers({ toFake: ['setTimeout', 'clearTimeout', 'Date', 'performance'] });
  port.owner = 'owner-a';
  port.get.mockReset();
});
afterEach(() => {
  vi.useRealTimers();
  vi.restoreAllMocks();
});

it('clears a previous account immediately and aborts its unfinished refresh', async () => {
  let finish: (value: unknown) => void = () => {};
  const pending = new Promise<unknown>(resolve => {
    finish = resolve;
  });
  port.get.mockResolvedValueOnce(environment('Europe/Paris')).mockReturnValueOnce(pending);
  const hook = renderHook(({ owner }) => useWorldEnvironment(owner, true), {
    initialProps: { owner: port.owner },
  });
  await settle();
  expect(hook.result.current.timezone).toBe('Europe/Paris');
  await act(async () => {
    vi.advanceTimersByTime(15 * 60_000);
  });
  const previous = port.get.mock.calls.at(-1)?.[1]?.signal as AbortSignal;
  port.owner = 'owner-b';
  port.get.mockResolvedValueOnce(environment('Asia/Tokyo'));
  hook.rerender({ owner: port.owner });
  expect(hook.result.current.timezone).toBeNull();
  await settle();
  expect(previous.aborted).toBe(true);
  expect(hook.result.current.timezone).toBe('Asia/Tokyo');
  await act(async () => finish(environment('America/New_York')));
  expect(hook.result.current.timezone).toBe('Asia/Tokyo');
  hook.unmount();
});

it('expires cached rain, pauses hidden refreshes and releases its timer', async () => {
  port.get.mockResolvedValue(environment('Europe/Paris', 1000));
  const hidden = vi.spyOn(document, 'hidden', 'get').mockReturnValue(false);
  const hook = renderHook(({ enabled }) => useWorldEnvironment(port.owner, enabled), {
    initialProps: { enabled: true },
  });
  await settle();
  expect(hook.result.current.weather).toBe('rain');
  await act(async () => {
    vi.advanceTimersByTime(30_000);
  });
  expect(hook.result.current.weather).toBe('neutral');
  hidden.mockReturnValue(true);
  act(() => document.dispatchEvent(new Event('visibilitychange')));
  await act(async () => {
    vi.advanceTimersByTime(20 * 60_000);
  });
  expect(port.get).toHaveBeenCalledTimes(1);
  hidden.mockReturnValue(false);
  act(() => document.dispatchEvent(new Event('visibilitychange')));
  await settle();
  expect(port.get).toHaveBeenCalledTimes(2);
  hook.rerender({ enabled: false });
  expect(hook.result.current.timezone).toBeNull();
  hook.unmount();
  expect(vi.getTimerCount()).toBe(0);
});
