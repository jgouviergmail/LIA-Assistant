import { act, renderHook, waitFor } from '@testing-library/react';
import { useState } from 'react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { makeUser } from '@/__tests__/factories';
import apiClient from '@/lib/api-client';
import { logger } from '@/lib/logger';
import type { User } from '@/lib/auth';
import { useIconStylePreference, type IconStylePreference } from '../useIconStylePreference';

function deferred<T>() {
  let resolve!: (value: T) => void;
  let reject!: (error: Error) => void;
  const promise = new Promise<T>((yes, no) => {
    resolve = yes;
    reject = no;
  });
  return { promise, resolve, reject };
}

function useTestAccount(initialUser = makeUser()) {
  const [user, setUser] = useState(initialUser);
  const preference = useIconStylePreference(user, updated => {
    setUser(previous => ({ ...previous, ...updated }));
    return true;
  });
  return { ...preference, syncAccount: setUser };
}

beforeEach(() => {
  vi.restoreAllMocks();
  vi.spyOn(logger, 'error').mockImplementation(() => {});
});

describe('account icon preference', () => {
  it('defaults to Fluent and reads a saved account preference', () => {
    const refresh = vi.fn(() => false);
    const { result, rerender } = renderHook<IconStylePreference, { user: User | null }>(
      ({ user }: { user: User | null }) => useIconStylePreference(user, refresh),
      { initialProps: { user: null } }
    );
    expect(result.current.style).toBe('fluent');
    rerender({ user: makeUser({ icon_style: 'lucide' }) });
    expect(result.current.style).toBe('lucide');
  });

  it('writes one request at a time and coalesces rapid changes to the latest choice', async () => {
    const first = deferred<User>();
    const patch = vi
      .spyOn(apiClient, 'patch')
      .mockReturnValueOnce(first.promise)
      .mockResolvedValue(makeUser({ icon_style: 'flex' }));
    const { result } = renderHook(() => useTestAccount());
    act(() => result.current.selectStyle('lucide'));
    act(() => result.current.selectStyle('fluent'));
    act(() => result.current.selectStyle('flex'));
    expect(result.current.style).toBe('flex');
    expect(patch).toHaveBeenCalledTimes(1);
    await act(async () => first.resolve(makeUser({ icon_style: 'lucide' })));
    await waitFor(() => expect(result.current.saving).toBe(false));
    expect(patch).toHaveBeenCalledTimes(2);
    expect(patch).toHaveBeenLastCalledWith(
      '/users/u1',
      { icon_style: 'flex' },
      expect.objectContaining({ signal: expect.any(AbortSignal) })
    );
    expect(result.current.style).toBe('flex');
  });

  it('restores the confirmed style on failure and retries the requested choice', async () => {
    const patch = vi
      .spyOn(apiClient, 'patch')
      .mockRejectedValueOnce(new Error('offline'))
      .mockResolvedValue(makeUser({ icon_style: 'flex' }));
    const { result } = renderHook(() => useTestAccount(makeUser({ icon_style: 'lucide' })));
    act(() => result.current.selectStyle('flex'));
    await waitFor(() => expect(result.current.failed).toBe(true));
    expect(result.current.style).toBe('lucide');
    act(() => result.current.retry());
    await waitFor(() => expect(result.current.saving).toBe(false));
    expect(result.current.failed).toBe(false);
    expect(result.current.style).toBe('flex');
    expect(patch).toHaveBeenCalledTimes(2);
  });

  it('does not treat an unconfirmed response as a saved preference', async () => {
    vi.spyOn(apiClient, 'patch').mockResolvedValue(makeUser({ icon_style: 'fluent' }));
    const { result } = renderHook(() => useTestAccount());
    act(() => result.current.selectStyle('flex'));
    await waitFor(() => expect(result.current.failed).toBe(true));
    expect(result.current.style).toBe('fluent');
  });

  it('continues to a newer choice after a failed earlier request', async () => {
    const first = deferred<User>();
    const patch = vi
      .spyOn(apiClient, 'patch')
      .mockReturnValueOnce(first.promise)
      .mockResolvedValue(makeUser({ icon_style: 'flex' }));
    const { result } = renderHook(() => useTestAccount());
    act(() => result.current.selectStyle('lucide'));
    act(() => result.current.selectStyle('flex'));
    await act(async () => first.reject(new Error('offline')));
    await waitFor(() => expect(result.current.saving).toBe(false));
    expect(patch).toHaveBeenCalledTimes(2);
    expect(result.current.failed).toBe(false);
    expect(result.current.style).toBe('flex');
  });

  it('publishes the confirmed profile without a second read and accepts later device updates', async () => {
    vi.spyOn(apiClient, 'patch').mockResolvedValue(makeUser({ icon_style: 'flex' }));
    const get = vi.spyOn(apiClient, 'get');
    const { result } = renderHook(() => useTestAccount());
    act(() => result.current.selectStyle('flex'));
    await waitFor(() => expect(result.current.saving).toBe(false));
    expect(result.current.style).toBe('flex');
    expect(get).not.toHaveBeenCalled();
    act(() => result.current.syncAccount(makeUser({ icon_style: 'lucide' })));
    expect(result.current.style).toBe('lucide');
  });

  it('accepts a later profile change after a failed write', async () => {
    vi.spyOn(apiClient, 'patch').mockRejectedValue(new Error('offline'));
    const { result } = renderHook(() => useTestAccount());
    act(() => result.current.selectStyle('flex'));
    await waitFor(() => expect(result.current.failed).toBe(true));
    act(() => result.current.syncAccount(makeUser({ icon_style: 'lucide' })));
    expect(result.current.style).toBe('lucide');
  });

  it('cancels on account unmount and never sends the queued write', async () => {
    const first = deferred<User>();
    const patch = vi.spyOn(apiClient, 'patch').mockReturnValue(first.promise);
    const refresh = vi.fn(() => true);
    const { result, unmount } = renderHook(() => useIconStylePreference(makeUser(), refresh));
    act(() => result.current.selectStyle('lucide'));
    act(() => result.current.selectStyle('flex'));
    const signal = patch.mock.calls[0][2]?.signal;
    unmount();
    expect(signal?.aborted).toBe(true);
    await act(async () => first.resolve(makeUser({ icon_style: 'lucide' })));
    expect(patch).toHaveBeenCalledTimes(1);
    expect(refresh).not.toHaveBeenCalled();
  });
});
