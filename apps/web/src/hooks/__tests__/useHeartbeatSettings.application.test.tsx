import { act, renderHook, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { publishApplicationResources } from '@/lib/application-resources';

const { get, patch, useAuth } = vi.hoisted(() => ({
  get: vi.fn(),
  patch: vi.fn(),
  useAuth: vi.fn(),
}));
vi.mock('@/hooks/useAuth', () => ({ useAuth }));
vi.mock('@/lib/api-client', async importOriginal => {
  const original = await importOriginal<typeof import('@/lib/api-client')>();
  return { ...original, default: { get, patch } };
});
import { useHeartbeatSettings, type HeartbeatSettings } from '../useHeartbeatSettings';

const saved: HeartbeatSettings = {
  heartbeat_enabled: true,
  heartbeat_notify_start_hour: 8,
  heartbeat_notify_end_hour: 22,
  available_sources: ['emails'],
  disabled_sources: [],
  all_sources: ['emails'],
};
beforeEach(() => {
  vi.resetAllMocks();
  useAuth.mockReturnValue({ user: { id: 'one' } });
  get.mockResolvedValue(saved);
});

describe('heartbeat account settings and native invalidation', () => {
  it('serializes writes and keeps the newer preview when the older request fails', async () => {
    let fail: ((reason: Error) => void) | undefined;
    let complete: ((value: HeartbeatSettings) => void) | undefined;
    patch
      .mockImplementationOnce(
        () =>
          new Promise<HeartbeatSettings>((_, reject) => {
            fail = reject;
          })
      )
      .mockImplementationOnce(
        () =>
          new Promise<HeartbeatSettings>(done => {
            complete = done;
          })
      );
    const { result } = renderHook(() => useHeartbeatSettings());
    await waitFor(() => expect(result.current.settings).toEqual(saved));
    let first: Promise<HeartbeatSettings | undefined> | undefined;
    let second: Promise<HeartbeatSettings | undefined> | undefined;
    act(() => {
      first = result.current.updateSettings({ heartbeat_disabled_sources: ['emails'] });
      second = result.current.updateSettings({ heartbeat_disabled_sources: [] });
    });
    await waitFor(() => expect(patch).toHaveBeenCalledTimes(1));
    await act(async () => {
      fail?.(new Error('offline'));
      await first;
    });
    await waitFor(() => expect(patch).toHaveBeenCalledTimes(2));
    expect(result.current.settings?.disabled_sources).toEqual([]);
    expect(get).toHaveBeenCalledTimes(1);
    await act(async () => {
      complete?.(saved);
      await second;
    });
    await waitFor(() => expect(get).toHaveBeenCalledTimes(2));
  });

  it('rereads authoritative values after an addressed native change', async () => {
    const { result } = renderHook(() => useHeartbeatSettings());
    await waitFor(() => expect(result.current.settings).toEqual(saved));
    get.mockResolvedValueOnce({ ...saved, heartbeat_enabled: false });
    act(() => publishApplicationResources('two', new Set(['heartbeat'])));
    expect(get).toHaveBeenCalledTimes(1);
    act(() => publishApplicationResources('one', new Set(['heartbeat'])));
    await waitFor(() => expect(result.current.settings?.heartbeat_enabled).toBe(false));
  });

  it('updates the displayed refusal list and rolls back a failed write', async () => {
    let fail: ((reason: Error) => void) | undefined;
    patch.mockImplementationOnce(
      () =>
        new Promise<HeartbeatSettings>((_, reject) => {
          fail = reject;
        })
    );
    const { result } = renderHook(() => useHeartbeatSettings());
    await waitFor(() => expect(result.current.settings).toEqual(saved));
    let writing: Promise<HeartbeatSettings | undefined> | undefined;
    act(() => {
      writing = result.current.updateSettings({ heartbeat_disabled_sources: ['emails'] });
    });
    await waitFor(() => expect(result.current.settings?.disabled_sources).toEqual(['emails']));
    await act(async () => {
      fail?.(new Error('offline'));
      await expect(writing).resolves.toBeUndefined();
    });
    await waitFor(() => expect(result.current.settings?.disabled_sources).toEqual([]));
  });

  it('hides the previous account and refuses its obsolete callback before HTTP', async () => {
    const { result, rerender } = renderHook(() => useHeartbeatSettings());
    await waitFor(() => expect(result.current.settings).toEqual(saved));
    const obsolete = result.current.updateSettings;
    get.mockImplementationOnce(() => new Promise<HeartbeatSettings>(() => {}));
    useAuth.mockReturnValue({ user: { id: 'two' } });
    rerender();
    expect(result.current.settings).toBeUndefined();
    await act(async () => {
      expect(await obsolete({ heartbeat_enabled: false })).toBeUndefined();
    });
    expect(patch).not.toHaveBeenCalled();
  });

  it('does not publish the late result of another account', async () => {
    let complete: ((value: HeartbeatSettings) => void) | undefined;
    patch.mockImplementationOnce(
      () =>
        new Promise<HeartbeatSettings>(done => {
          complete = done;
        })
    );
    const { result, rerender } = renderHook(() => useHeartbeatSettings());
    await waitFor(() => expect(result.current.settings).toEqual(saved));
    let writing: Promise<HeartbeatSettings | undefined> | undefined;
    act(() => {
      writing = result.current.updateSettings({ heartbeat_enabled: false });
    });
    useAuth.mockReturnValue({ user: { id: 'two' } });
    get.mockResolvedValueOnce({ ...saved, heartbeat_notify_start_hour: 11 });
    rerender();
    await waitFor(() => expect(result.current.settings?.heartbeat_notify_start_hour).toBe(11));
    await act(async () => {
      complete?.({ ...saved, heartbeat_enabled: false });
      await writing;
    });
    expect(result.current.settings?.heartbeat_enabled).toBe(true);
    expect(result.current.settings?.heartbeat_notify_start_hour).toBe(11);
  });
});
