/** Public availability must recover after a transient dev worker restart. */
import { act, renderHook } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { ApiError } from '@/lib/api-client';
import { useAuthFeatures, type AuthFeatures } from '../useWebAuthn';

const { get } = vi.hoisted(() => ({ get: vi.fn() }));
vi.mock('@/lib/api-client', async importOriginal => {
  const original = await importOriginal<typeof import('@/lib/api-client')>();
  return { ...original, default: { get } };
});
vi.mock('@/lib/logger', () => ({ logger: { error: vi.fn(), debug: vi.fn(), warn: vi.fn() } }));

const disabled: AuthFeatures = { mfa_enabled: false, federated_signin_enabled: false,
  terms_required: false, terms_version: 'controlled-terms' };
beforeEach(() => { vi.useFakeTimers(); get.mockReset(); });
afterEach(() => { vi.useRealTimers(); });

describe('public authentication feature recovery', () => {
  it.each(['Failed to fetch', 'Load failed', 'NetworkError when attempting to fetch resource.', 'The operation was aborted due to timeout'])('recovers initial %s without a reload and preserves disabled flags', async message => {
    get.mockRejectedValueOnce(new TypeError(message)).mockResolvedValue(disabled);
    const { result } = renderHook(() => useAuthFeatures());
    await act(async () => {});
    expect(result.current.features).toBeUndefined();
    await act(async () => { await vi.advanceTimersByTimeAsync(2000); });
    expect(result.current.features).toEqual(disabled);
    expect(get).toHaveBeenCalledTimes(2);
    await act(async () => { await vi.advanceTimersByTimeAsync(120000); });
    expect(get).toHaveBeenCalledTimes(2);
  });

  it('stops automatic retries on a persistent outage and resumes when the network returns', async () => {
    get.mockRejectedValue(new TypeError('Failed to fetch'));
    const { result } = renderHook(() => useAuthFeatures());
    await act(async () => {});
    for (let period = 0; period < 8; period += 1) {
      await act(async () => { await vi.advanceTimersByTimeAsync(30000); });
    }
    const attempts = get.mock.calls.length;
    expect(attempts).toBeGreaterThan(1);
    expect(attempts).toBeLessThanOrEqual(7);
    await act(async () => { await vi.advanceTimersByTimeAsync(120000); });
    expect(get).toHaveBeenCalledTimes(attempts);
    get.mockResolvedValue(disabled);
    await act(async () => { window.dispatchEvent(new Event('online')); });
    expect(result.current.features).toEqual(disabled);
  });

  it.each([400, 401, 403, 429, 500])('does not retry a nontransient HTTP %i refusal', async status => {
    get.mockRejectedValue(new ApiError('Refused', status));
    renderHook(() => useAuthFeatures());
    await act(async () => {});
    await act(async () => { await vi.advanceTimersByTimeAsync(120000); });
    await act(async () => { window.dispatchEvent(new Event('online')); window.dispatchEvent(new Event('focus')); });
    expect(get).toHaveBeenCalledTimes(1);
  });

  it('cancels scheduled recovery after the consumer unmounts', async () => {
    get.mockRejectedValue(new TypeError('Failed to fetch'));
    const { unmount } = renderHook(() => useAuthFeatures());
    await act(async () => {});
    unmount();
    window.dispatchEvent(new Event('online'));
    await act(async () => { await vi.advanceTimersByTimeAsync(120000); });
    expect(get).toHaveBeenCalledTimes(1);
  });

  it('coalesces simultaneous network, focus and mobile visibility recovery signals', async () => {
    get.mockRejectedValueOnce(new TypeError('Failed to fetch'));
    const { result } = renderHook(() => useAuthFeatures());
    await act(async () => {});
    const pending = Promise.withResolvers<typeof disabled>();
    get.mockReturnValue(pending.promise);
    act(() => {
      window.dispatchEvent(new Event('online'));
      window.dispatchEvent(new Event('focus'));
      document.dispatchEvent(new Event('visibilitychange'));
    });
    expect(get).toHaveBeenCalledTimes(2);
    await act(async () => { pending.resolve(disabled); });
    expect(result.current.features).toEqual(disabled);
  });
});
