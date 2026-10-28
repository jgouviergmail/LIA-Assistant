import { StrictMode } from 'react';
import { act, renderHook } from '@testing-library/react';
import { expect, it, vi } from 'vitest';
import { useEffectRequest } from '../useEffectRequest';

it('does not send the disposable Strict Mode setup request', async () => {
  const request = vi.fn();
  const { unmount } = renderHook(() => useEffectRequest(request), { wrapper: StrictMode });
  await act(async () => {});
  expect(request).toHaveBeenCalledTimes(1);
  const signal: AbortSignal = request.mock.calls[0][0];
  expect(signal.aborted).toBe(false);
  unmount();
  expect(signal.aborted).toBe(true);
});

it('cancels an unsent request on immediate unmount', async () => {
  const request = vi.fn();
  const { unmount } = renderHook(() => useEffectRequest(request));
  unmount();
  await act(async () => {});
  expect(request).not.toHaveBeenCalled();
});

it('aborts the old lifetime before starting the replacement request', async () => {
  const first = vi.fn();
  const next = vi.fn();
  const { rerender } = renderHook(({ read }) => useEffectRequest(read), {
    initialProps: { read: first },
  });
  await act(async () => {});
  const previous: AbortSignal = first.mock.calls[0][0];
  rerender({ read: next });
  expect(previous.aborted).toBe(true);
  await act(async () => {});
  expect(first).toHaveBeenCalledTimes(1);
  expect(next).toHaveBeenCalledTimes(1);
});

it('runs a manual read in the same generation: it supersedes the read in flight', async () => {
  const request = vi.fn((signal: AbortSignal) => signal);
  const { result } = renderHook(() => useEffectRequest(request));
  await act(async () => {});
  const automatic: AbortSignal = request.mock.calls[0][0];

  let manual: AbortSignal | undefined;
  await act(async () => {
    manual = await result.current();
  });

  expect(request).toHaveBeenCalledTimes(2);
  expect(automatic.aborted).toBe(true);
  expect(manual?.aborted).toBe(false);

  await act(async () => {
    await result.current();
  });
  expect(manual?.aborted).toBe(true);
});

it('lets the replacement request abort a manual read still in flight', async () => {
  const first = vi.fn((signal: AbortSignal) => signal);
  const next = vi.fn();
  const { result, rerender } = renderHook(({ read }) => useEffectRequest(read), {
    initialProps: { read: first },
  });
  await act(async () => {});
  let manual: AbortSignal | undefined;
  await act(async () => {
    manual = await result.current();
  });
  expect(manual?.aborted).toBe(false);

  rerender({ read: next });

  expect(manual?.aborted).toBe(true);
});

it('sends nothing from a retained manual read once its request is obsolete', async () => {
  const first = vi.fn();
  const next = vi.fn();
  const { result, rerender } = renderHook(({ read }) => useEffectRequest(read), {
    initialProps: { read: first },
  });
  await act(async () => {});
  const retained = result.current;
  rerender({ read: next });
  await act(async () => {});

  await expect(retained()).resolves.toBeUndefined();

  expect(first).toHaveBeenCalledTimes(1);
  expect(next).toHaveBeenCalledTimes(1);
});

it('sends nothing from a manual read after unmount', async () => {
  const request = vi.fn();
  const { result, unmount } = renderHook(() => useEffectRequest(request));
  await act(async () => {});
  const retained = result.current;
  unmount();

  await expect(retained()).resolves.toBeUndefined();

  expect(request).toHaveBeenCalledTimes(1);
});

it('hands the manual read its answer', async () => {
  const request = vi.fn(async () => 'answer');
  const { result } = renderHook(() => useEffectRequest(request));
  await act(async () => {});

  let answer: string | undefined;
  await act(async () => {
    answer = await result.current();
  });

  expect(answer).toBe('answer');
});
