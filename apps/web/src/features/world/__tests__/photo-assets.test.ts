import { afterEach, expect, it, vi } from 'vitest';
import { preparePhotoAsset } from '../photo-assets';
afterEach(() => vi.useRealTimers());
it('bounds a stalled atlas and leaves no timer after readiness', async () => {
  vi.useFakeTimers();
  const stalled = preparePhotoAsset(new Promise(() => {}), new AbortController().signal);
  await vi.advanceTimersByTimeAsync(1500);
  await stalled;
  expect(vi.getTimerCount()).toBe(0);
  await preparePhotoAsset(
    Promise.reject(new Error('asset unavailable')),
    new AbortController().signal
  );
  expect(vi.getTimerCount()).toBe(0);
});
it('withdraws an aborted preparation without waiting for image decoding', async () => {
  vi.useFakeTimers();
  const controller = new AbortController();
  const pending = preparePhotoAsset(new Promise(() => {}), controller.signal);
  const rejected = expect(pending).rejects.toThrow('Aborted');
  controller.abort();
  await rejected;
  expect(vi.getTimerCount()).toBe(0);
});
