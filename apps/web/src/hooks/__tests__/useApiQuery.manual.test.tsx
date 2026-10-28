import { StrictMode } from 'react';
import { act, renderHook, waitFor } from '@testing-library/react';
import { beforeEach, expect, it, vi } from 'vitest';
import { useApiQuery } from '../useApiQuery';

const { get } = vi.hoisted(() => ({ get: vi.fn() }));
vi.mock('@/lib/api-client', async original => ({
  ...(await original<typeof import('@/lib/api-client')>()),
  default: { get },
}));
vi.mock('@/lib/logger', () => ({ logger: { error: vi.fn() } }));
beforeEach(() => {
  get.mockReset();
});

it('keeps manual reads enabled without spending on mount, Strict Mode or reactivation', async () => {
  get.mockResolvedValue({ value: 'accepted' });
  const { result, rerender } = renderHook(
    ({ enabled }) =>
      useApiQuery<{ value: string }>('/manual', {
        componentName: 'ManualQuery',
        enabled,
        autoFetch: false,
      }),
    { initialProps: { enabled: true }, wrapper: StrictMode }
  );
  await act(async () => {});
  expect(get).not.toHaveBeenCalled();
  expect(result.current.loading).toBe(false);
  await act(async () => {
    expect(await result.current.refetchVerified()).toBe(true);
  });
  expect(result.current.data).toEqual({ value: 'accepted' });
  rerender({ enabled: false });
  rerender({ enabled: true });
  await act(async () => {});
  expect(get).toHaveBeenCalledTimes(1);
});

it('aborts a manual read on suspension and rejects its late response and retained callback', async () => {
  const pending = Promise.withResolvers<{ value: string }>();
  get.mockReturnValue(pending.promise);
  const { result, rerender } = renderHook(
    ({ enabled }) =>
      useApiQuery<{ value: string }>('/manual', {
        componentName: 'ManualQuery',
        enabled,
        autoFetch: false,
      }),
    { initialProps: { enabled: true } }
  );
  let read: Promise<boolean>;
  act(() => {
    read = result.current.refetchVerified();
  });
  await waitFor(() => expect(get).toHaveBeenCalledOnce());
  const retained = result.current.refetchVerified;
  const signal: AbortSignal = get.mock.calls[0][1].signal;
  rerender({ enabled: false });
  expect(signal.aborted).toBe(true);
  rerender({ enabled: true });
  await act(async () => {});
  expect(result.current.loading).toBe(false);
  await act(async () => {
    pending.resolve({ value: 'late' });
    await read;
  });
  expect(result.current.data).toBeUndefined();
  expect(await retained()).toBe(false);
  expect(get).toHaveBeenCalledTimes(1);
});
