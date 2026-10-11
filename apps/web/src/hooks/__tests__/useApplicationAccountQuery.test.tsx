import { act, renderHook, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

const { useAuth, get } = vi.hoisted(() => ({ useAuth: vi.fn(), get: vi.fn() }));
vi.mock('@/hooks/useAuth', () => ({ useAuth }));
vi.mock('@/lib/api-client', async importOriginal => {
  const original = await importOriginal<typeof import('@/lib/api-client')>();
  return { ...original, default: { get } };
});
import { useApplicationAccountQuery } from '../useApplicationAccountQuery';

beforeEach(() => {
  vi.clearAllMocks();
  useAuth.mockReturnValue({ user: { id: 'one' } });
});

describe('application account queries', () => {
  it('hides the old account value while the new account is loading', async () => {
    get.mockResolvedValueOnce({ value: 'private-one' });
    let resolve: ((value: { value: string }) => void) | undefined;
    get.mockImplementationOnce(() => new Promise<{ value: string }>(done => { resolve = done; }));
    const { result, rerender } = renderHook(() => useApplicationAccountQuery<{ value: string }>('/briefing/preferences', 'test'));
    await waitFor(() => expect(result.current.data?.value).toBe('private-one'));
    useAuth.mockReturnValue({ user: { id: 'two' } });
    rerender();
    expect(result.current.data).toBeUndefined();
    await waitFor(() => expect(get).toHaveBeenCalledTimes(2));
    await act(async () => { resolve?.({ value: 'private-two' }); });
    expect(result.current.data?.value).toBe('private-two');
  });

  it('does not read account settings when logged out', async () => {
    useAuth.mockReturnValue({ user: null });
    const { result } = renderHook(() => useApplicationAccountQuery('/chat/shortcuts', 'test'));
    await act(async () => { await result.current.refetch(); });
    expect(get).not.toHaveBeenCalled();
    expect(result.current.data).toBeUndefined();
  });

  it('requires a fresh value when returning to an earlier account lifetime', async () => {
    get.mockResolvedValueOnce({ value: 'previous-one' });
    get.mockImplementationOnce(() => new Promise(() => {}));
    get.mockImplementationOnce(() => new Promise(() => {}));
    const { result, rerender } = renderHook(() => useApplicationAccountQuery<{ value: string }>('/chat/shortcuts', 'test'));
    await waitFor(() => expect(result.current.data?.value).toBe('previous-one'));
    useAuth.mockReturnValue({ user: { id: 'two' } });
    rerender();
    await waitFor(() => expect(get).toHaveBeenCalledTimes(2));
    useAuth.mockReturnValue({ user: { id: 'one' } });
    rerender();
    expect(result.current.data).toBeUndefined();
    await waitFor(() => expect(get).toHaveBeenCalledTimes(3));
    expect(result.current.data).toBeUndefined();
  });

  it('refuses an obsolete refresh callback before issuing HTTP for another account', async () => {
    get.mockResolvedValueOnce({ value: 'one' });
    const { result, rerender } = renderHook(() => useApplicationAccountQuery<{ value: string }>('/chat/shortcuts', 'test'));
    await waitFor(() => expect(result.current.data?.value).toBe('one'));
    const obsolete = result.current.refetch;
    get.mockImplementationOnce(() => new Promise(() => {}));
    useAuth.mockReturnValue({ user: { id: 'two' } });
    rerender();
    await waitFor(() => expect(get).toHaveBeenCalledTimes(2));
    await act(async () => { await obsolete(); });
    expect(get).toHaveBeenCalledTimes(2);
  });

  it('reports an unsuccessful reread while preserving the last verified value', async () => {
    get.mockResolvedValueOnce({ value: 'saved' });
    const { result } = renderHook(() => useApplicationAccountQuery<{ value: string }>('/chat/shortcuts', 'test'));
    await waitFor(() => expect(result.current.data?.value).toBe('saved'));
    get.mockRejectedValueOnce(new Error('offline'));
    await act(async () => { await expect(result.current.refetch()).rejects.toThrow('Application state refresh failed'); });
    expect(result.current.data?.value).toBe('saved');
    expect(result.current.error).toBeTruthy();
  });

  it('isolates functional local updates from data belonging to the previous lifetime', async () => {
    get.mockResolvedValueOnce({ count: 50 });
    const { result, rerender } = renderHook(() => useApplicationAccountQuery<{ count: number }>('/connectors?fresh=true', 'test'));
    await waitFor(() => expect(result.current.data?.count).toBe(50));
    const obsolete = result.current.setData;
    useAuth.mockReturnValue({ user: { id: 'two' } });
    get.mockImplementationOnce(() => new Promise(() => {}));
    rerender();
    await act(async () => { result.current.setData(previous => ({ count: (previous?.count ?? 0) + 1 })); });
    expect(result.current.data?.count).toBe(1);
    await act(async () => { obsolete({ count: 100 }); });
    expect(result.current.data?.count).toBe(1);
  });

  it('replaces a manual local update with the next verified reread', async () => {
    get.mockResolvedValueOnce({ count: 1 });
    const { result } = renderHook(() => useApplicationAccountQuery<{ count: number }>('/connectors?fresh=true', 'test'));
    await waitFor(() => expect(result.current.data?.count).toBe(1));
    act(() => result.current.setData({ count: 2 }));
    expect(result.current.data?.count).toBe(2);
    get.mockResolvedValueOnce({ count: 3 });
    await act(async () => { await result.current.refetch(); });
    expect(result.current.data?.count).toBe(3);
  });
});
