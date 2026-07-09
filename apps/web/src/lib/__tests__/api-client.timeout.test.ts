/**
 * Regression tests for api-client timeout signal handling (2026-07 audit, wave 1).
 *
 * createAbortSignal() used a bare `setTimeout(() => controller.abort(), timeout)`
 * that was never cleared: every completed request left a pending timer alive for
 * the full timeout duration (timer/GC pressure, noisy aborts on settled requests).
 * The fix uses AbortSignal.timeout(), which owns its timer lifecycle.
 */

import { afterEach, describe, expect, it, vi } from 'vitest';

import { apiClient } from '@/lib/api-client';

const jsonResponse = () =>
  new Response('{"ok":true}', {
    status: 200,
    headers: { 'content-type': 'application/json' },
  });

describe('api-client timeout signal', () => {
  afterEach(() => {
    vi.unstubAllGlobals();
    vi.useRealTimers();
  });

  it('does not leak a pending abort timer after the request completes', async () => {
    vi.useFakeTimers();
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(jsonResponse()));

    await apiClient.get('/api/v1/health', { timeout: 30_000 });

    // Before the fix, the un-cleared setTimeout stayed pending for 30s
    expect(vi.getTimerCount()).toBe(0);
  });

  it('aborts the request with a TimeoutError once the timeout elapses', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockImplementation(
        (_url: string, init: RequestInit) =>
          new Promise((_resolve, reject) => {
            init.signal?.addEventListener('abort', () => {
              reject((init.signal as AbortSignal).reason);
            });
          })
      )
    );

    await expect(apiClient.get('/api/v1/slow', { timeout: 20 })).rejects.toMatchObject({
      name: 'TimeoutError',
    });
  });
});
