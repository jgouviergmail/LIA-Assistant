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
import { useAdminMCPServers } from '../useAdminMCPServers';

const server = {
  server_key: 'shared',
  name: 'Shared',
  description: null,
  tools_count: 1,
  tools: [{ name: 'read', description: 'Read' }],
  enabled_for_user: true,
};
beforeEach(() => {
  vi.resetAllMocks();
  useAuth.mockReturnValue({ user: { id: 'one' } });
  get.mockResolvedValue([server]);
});

describe('personal shared MCP account lifetime', () => {
  it('rereads only the account addressed by the committed native change', async () => {
    const { result } = renderHook(() => useAdminMCPServers());
    await waitFor(() => expect(result.current.servers).toEqual([server]));
    get.mockResolvedValueOnce([{ ...server, enabled_for_user: false }]);
    act(() => publishApplicationResources('two', new Set(['shared_mcp_preferences'])));
    expect(get).toHaveBeenCalledTimes(1);
    act(() => publishApplicationResources('one', new Set(['shared_mcp_preferences'])));
    await waitFor(() => expect(result.current.servers[0].enabled_for_user).toBe(false));
  });

  it('hides previous data and refuses a callback from the previous account before HTTP', async () => {
    const { result, rerender } = renderHook(() => useAdminMCPServers());
    await waitFor(() => expect(result.current.servers).toEqual([server]));
    const obsolete = result.current.toggleServer;
    useAuth.mockReturnValue({ user: { id: 'two' } });
    get.mockImplementationOnce(() => new Promise(() => {}));
    rerender();
    expect(result.current.servers).toEqual([]);
    await act(async () => {
      expect(await obsolete('shared')).toBeUndefined();
    });
    expect(patch).not.toHaveBeenCalled();
  });

  it('keeps last known values when a native reread fails', async () => {
    const { result } = renderHook(() => useAdminMCPServers());
    await waitFor(() => expect(result.current.servers).toEqual([server]));
    get.mockRejectedValueOnce(new Error('offline'));
    act(() => publishApplicationResources('one', new Set(['shared_mcp_preferences'])));
    await waitFor(() => expect(get).toHaveBeenCalledTimes(2));
    expect(result.current.servers).toEqual([server]);
  });

  it('suppresses late toggle results after an account transition', async () => {
    let complete: ((value: { server_key: string; enabled_for_user: boolean }) => void) | undefined;
    patch.mockImplementationOnce(
      () =>
        new Promise(done => {
          complete = done;
        })
    );
    const { result, rerender } = renderHook(() => useAdminMCPServers());
    await waitFor(() => expect(result.current.servers).toEqual([server]));
    let pending: ReturnType<typeof result.current.toggleServer> | undefined;
    act(() => {
      pending = result.current.toggleServer('shared');
    });
    useAuth.mockReturnValue({ user: { id: 'two' } });
    get.mockResolvedValueOnce([]);
    rerender();
    await act(async () => {
      complete?.({ server_key: 'shared', enabled_for_user: false });
      expect(await pending).toBeUndefined();
    });
    expect(result.current.servers).toEqual([]);
    expect(get).toHaveBeenCalledTimes(2);
  });
});
