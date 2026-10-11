import { act, renderHook, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import type { ApplicationStateChange } from '@/types/application-state';
import { subscribeApplicationResource } from '@/lib/application-resources';

const { useAuth, refreshUser } = vi.hoisted(() => ({ useAuth: vi.fn(), refreshUser: vi.fn() }));
vi.mock('@/hooks/useAuth', () => ({ useAuth }));
const { push } = vi.hoisted(() => ({ push: vi.fn() }));
vi.mock('next/navigation', () => ({ useRouter: () => ({ push }) }));
const { get, stopAvatar, bump } = vi.hoisted(() => ({
  get: vi.fn(), stopAvatar: vi.fn(), bump: vi.fn(),
}));
vi.mock('@/lib/api-client', () => ({ apiClient: { get } }));
vi.mock('@/lib/avatars/runtime', () => ({ stopAvatarForConnectorChange: stopAvatar }));
vi.mock('@/stores/revisionStore', () => ({ bumpRevision: bump }));

import { useApplicationStateSync } from '../useApplicationStateSync';

const actorId = '00000000-0000-4000-8000-000000000001';
const change: ApplicationStateChange = {
  schema_version: 1,
  command_id: '00000000-0000-4000-8000-000000000002',
  actor_id: actorId,
  resources: ['profile'],
  changed_fields: ['font_size'],
  observed_at: '2026-10-06T17:00:00Z',
};

beforeEach(() => {
  vi.clearAllMocks();
  refreshUser.mockResolvedValue(true);
  get.mockResolvedValue({ connectors: [] });
  stopAvatar.mockResolvedValue(undefined);
  useAuth.mockReturnValue({ user: { id: actorId }, refreshUser });
});

describe('confirmed application state synchronization', () => {
  it('invalidates Live reflex readers without restarting a session or refreshing the profile', async () => {
    const read = vi.fn();
    const unsubscribe = subscribeApplicationResource(actorId, 'live_preferences', read);
    const { result } = renderHook(() => useApplicationStateSync());
    act(() => result.current.handleChange({ ...change, resources: ['live_preferences'], changed_fields: ['live_reflexes'] }));
    await waitFor(() => expect(read).toHaveBeenCalledOnce());
    expect(refreshUser).not.toHaveBeenCalled();
    expect(stopAvatar).not.toHaveBeenCalled();
    expect(bump).not.toHaveBeenCalled();
    unsubscribe();
  });
  it('rereads saved connections before stopping the avatar and invalidating its readers', async () => {
    const { result } = renderHook(() => useApplicationStateSync());
    act(() => result.current.handleChange({ ...change, resources: ['connectors', 'avatar'], changed_fields: ['connector_to_disconnect'] }));
    await waitFor(() => expect(bump).toHaveBeenCalledWith('avatar'));
    expect(get).toHaveBeenCalledWith('/connectors?fresh=true');
    expect(stopAvatar).toHaveBeenCalledOnce();
  });
  it('does not stop an unrelated avatar when removing a Live connector', async () => {
    const { result } = renderHook(() => useApplicationStateSync());
    act(() => result.current.handleChange({ ...change, resources: ['connectors', 'live_connectors'], changed_fields: ['connector_to_disconnect'] }));
    await waitFor(() => expect(bump).toHaveBeenCalledWith('live_connectors'));
    expect(stopAvatar).not.toHaveBeenCalled();
  });
  it('preserves runtimes when the authoritative connection read fails', async () => {
    get.mockRejectedValue(new Error('offline'));
    const { result } = renderHook(() => useApplicationStateSync());
    act(() => result.current.handleChange({ ...change, resources: ['connectors', 'avatar'], changed_fields: ['connector_to_disconnect'] }));
    await act(async () => {});
    expect(get).toHaveBeenCalledOnce();
    expect(stopAvatar).not.toHaveBeenCalled();
    expect(bump).not.toHaveBeenCalled();
  });
  it('discards an old-account connection refresh before touching any runtime', async () => {
    let finish: (value: { connectors: [] }) => void = () => {};
    get.mockImplementationOnce(() => new Promise(done => { finish = done; }));
    const { result, rerender } = renderHook(() => useApplicationStateSync());
    act(() => result.current.handleChange({ ...change, resources: ['connectors', 'avatar'], changed_fields: ['connector_to_disconnect'] }));
    useAuth.mockReturnValue({ user: { id: 'other' }, refreshUser });
    rerender();
    await act(async () => { finish({ connectors: [] }); });
    expect(stopAvatar).not.toHaveBeenCalled();
    expect(bump).not.toHaveBeenCalled();
  });
  it('does not bump a new account after waiting for the old avatar to close', async () => {
    let finish: () => void = () => {};
    stopAvatar.mockImplementationOnce(() => new Promise<void>(done => { finish = done; }));
    const { result, rerender } = renderHook(() => useApplicationStateSync());
    act(() => result.current.handleChange({ ...change, resources: ['connectors', 'avatar'], changed_fields: ['connector_to_disconnect'] }));
    await waitFor(() => expect(stopAvatar).toHaveBeenCalledOnce());
    useAuth.mockReturnValue({ user: { id: 'other' }, refreshUser });
    rerender();
    await act(async () => { finish(); });
    expect(bump).not.toHaveBeenCalled();
  });
  it('refreshes heartbeat through its owner without an unrelated profile request', async () => {
    refreshUser.mockRejectedValue(new Error('profile offline'));
    const read = vi.fn();
    const unsubscribe = subscribeApplicationResource(actorId, 'heartbeat', read);
    const { result } = renderHook(() => useApplicationStateSync());
    try {
      act(() => result.current.handleChange({ ...change, resources: ['heartbeat'], changed_fields: ['heartbeat_enabled'] }));
      await waitFor(() => expect(read).toHaveBeenCalledOnce());
      expect(refreshUser).not.toHaveBeenCalled();
    } finally { unsubscribe(); }
  });
  it('waits for transport completion before navigating to the verified saved locale', async () => {
    window.history.replaceState({}, '', '/dashboard/chat?view=compact#thread');
    useAuth.mockReturnValue({ user: { id: actorId, language: 'fr' }, refreshUser });
    const { result, rerender } = renderHook(() => useApplicationStateSync());
    act(() => result.current.handleChange({ ...change, changed_fields: ['language'] }));
    await act(async () => {});
    useAuth.mockReturnValue({ user: { id: actorId, language: 'zh-CN' }, refreshUser });
    rerender();
    expect(push).not.toHaveBeenCalled();
    act(() => result.current.completeStream());
    expect(push).toHaveBeenCalledWith('/zh/dashboard/chat?view=compact#thread');
    expect(document.cookie).toContain('NEXT_LOCALE=zh');
  });

  it('does not navigate from a hint when its authoritative refresh failed', async () => {
    refreshUser.mockResolvedValue(false);
    useAuth.mockReturnValue({ user: { id: actorId, language: 'en' }, refreshUser });
    const { result } = renderHook(() => useApplicationStateSync());
    act(() => result.current.handleChange({ ...change, changed_fields: ['language'] }));
    await act(async () => {});
    act(() => result.current.completeStream());
    expect(push).not.toHaveBeenCalled();
  });
  it('refreshes its own account without replacing a focused form or chat draft', async () => {
    const input = document.createElement('input');
    input.value = 'unsaved question';
    document.body.append(input);
    input.focus();
    const { result } = renderHook(() => useApplicationStateSync());
    act(() => result.current.handleChange(change));
    await waitFor(() => expect(refreshUser).toHaveBeenCalledTimes(1));
    expect(document.activeElement).toBe(input);
    expect(input.value).toBe('unsaved question');
    input.remove();
  });

  it('ignores events for another account and events after logout', () => {
    const { result, rerender } = renderHook(() => useApplicationStateSync());
    act(() => result.current.handleChange({ ...change, actor_id: '00000000-0000-4000-8000-000000000099' }));
    useAuth.mockReturnValue({ user: null, refreshUser });
    rerender();
    act(() => result.current.handleChange(change));
    expect(refreshUser).not.toHaveBeenCalled();
  });

  it('rejects a retained event callback after returning to the same account', async () => {
    const { result, rerender } = renderHook(() => useApplicationStateSync());
    const oldCallback = result.current.handleChange;
    useAuth.mockReturnValue({ user: { id: 'other' }, refreshUser });
    rerender();
    useAuth.mockReturnValue({ user: { id: actorId }, refreshUser });
    rerender();
    act(() => oldCallback(change));
    await act(async () => {});
    expect(refreshUser).not.toHaveBeenCalled();
  });

  it('coalesces a burst while rereading once more for a change committed during the first read', async () => {
    let resolve: (value: boolean) => void = () => {};
    refreshUser.mockImplementationOnce(() => new Promise<boolean>(done => { resolve = done; }));
    const { result } = renderHook(() => useApplicationStateSync());
    act(() => { result.current.handleChange(change); result.current.handleChange(change); result.current.handleChange(change); });
    expect(refreshUser).toHaveBeenCalledTimes(1);
    await act(async () => { resolve(true); });
    await waitFor(() => expect(refreshUser).toHaveBeenCalledTimes(2));
  });

  it('does not continue an obsolete refresh loop after switching accounts', async () => {
    let resolve: (value: boolean) => void = () => {};
    refreshUser.mockImplementationOnce(() => new Promise<boolean>(done => { resolve = done; }));
    const { result, rerender } = renderHook(() => useApplicationStateSync());
    act(() => { result.current.handleChange(change); result.current.handleChange(change); });
    useAuth.mockReturnValue({ user: { id: '00000000-0000-4000-8000-000000000099' }, refreshUser });
    rerender();
    await act(async () => { resolve(true); });
    expect(refreshUser).toHaveBeenCalledTimes(1);
  });
});
