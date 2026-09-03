/**
 * The screen wake lock: acquired when the API exists, re-acquired when the
 * page comes back, released once and for all on demand, absent otherwise.
 */

import { afterEach, describe, expect, it, vi } from 'vitest';

import { acquireWakeLock, isWakeLockSupported } from '../wake-lock';

function installWakeLock(request: () => Promise<{ release: () => Promise<void> }>) {
  Object.defineProperty(navigator, 'wakeLock', { value: { request }, configurable: true });
}

afterEach(() => {
  Reflect.deleteProperty(navigator, 'wakeLock');
});

describe('acquireWakeLock', () => {
  it('returns null where the API is absent', async () => {
    expect(isWakeLockSupported()).toBe(false);
    expect(await acquireWakeLock()).toBeNull();
  });

  it('requests a screen lock, re-requests it on visibility, and stops after release', async () => {
    const release = vi.fn(async () => undefined);
    const request = vi.fn(async () => ({ release }));
    installWakeLock(request);
    expect(isWakeLockSupported()).toBe(true);

    const handle = await acquireWakeLock();
    expect(handle).not.toBeNull();
    expect(request).toHaveBeenCalledWith('screen');

    Object.defineProperty(document, 'visibilityState', { value: 'visible', configurable: true });
    document.dispatchEvent(new Event('visibilitychange'));
    await Promise.resolve();
    expect(request).toHaveBeenCalledTimes(2);

    await handle!.release();
    expect(release).toHaveBeenCalledTimes(1);
    document.dispatchEvent(new Event('visibilitychange'));
    await Promise.resolve();
    expect(request).toHaveBeenCalledTimes(2);
  });

  it('returns null when the browser refuses the lock', async () => {
    installWakeLock(vi.fn(async () => Promise.reject(new Error('low battery'))));
    expect(await acquireWakeLock()).toBeNull();
  });
});
