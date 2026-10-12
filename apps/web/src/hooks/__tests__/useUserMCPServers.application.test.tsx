import { act, renderHook, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { useUserMCPServers } from '../useUserMCPServers';
import { userMCPServer } from './user-mcp-fixture';
import { publishApplicationResources } from '@/lib/application-resources';

const mocks = vi.hoisted(() => ({
  auth: vi.fn(),
  get: vi.fn(),
  post: vi.fn(),
  patch: vi.fn(),
  delete: vi.fn(),
}));
vi.mock('@/hooks/useAuth', () => ({ useAuth: mocks.auth }));
vi.mock('@/lib/api-client', async () => ({
  ...(await vi.importActual<typeof import('@/lib/api-client')>('@/lib/api-client')),
  default: { get: mocks.get, post: mocks.post, patch: mocks.patch, delete: mocks.delete },
}));

beforeEach(() => {
  mocks.auth.mockReturnValue({ user: { id: 'owner' } });
  mocks.get
    .mockReset()
    .mockResolvedValue({ servers: [userMCPServer({ name: 'private-owned-server' })], total: 1 });
  mocks.post.mockReset();
  mocks.patch.mockReset();
  mocks.delete.mockReset();
});

describe('personal MCP account and plugin-group refresh', () => {
  it('hides previous-account endpoint metadata before the next response', async () => {
    const { result, rerender } = renderHook(() => useUserMCPServers());
    await waitFor(() => expect(result.current.servers[0]?.name).toBe('private-owned-server'));
    mocks.get.mockImplementation(() => new Promise(() => {}));
    await act(async () => {
      mocks.auth.mockReturnValue({ user: { id: 'other' } });
      rerender();
    });
    expect(result.current.servers).toEqual([]);
  });

  it('refetches only the current account MCP list after a group change', async () => {
    const { result } = renderHook(() => useUserMCPServers());
    await waitFor(() => expect(result.current.total).toBe(1));
    act(() => publishApplicationResources('other', new Set(['user_mcp'])));
    expect(mocks.get).toHaveBeenCalledTimes(1);
    mocks.get.mockResolvedValue({ servers: [], total: 0 });
    act(() => publishApplicationResources('owner', new Set(['user_mcp'])));
    await waitFor(() => expect(result.current.total).toBe(0));
  });

  it('rejects retained old-account writes and OAuth initiation before requesting', async () => {
    const { result, rerender } = renderHook(() => useUserMCPServers());
    const { createServer, deleteServer, initiateOAuth } = result.current;
    mocks.auth.mockReturnValue({ user: { id: 'other' } });
    rerender();
    await act(async () => {
      await expect(
        createServer({ name: 'new', url: 'https://example.com', auth_type: 'none' })
      ).rejects.toThrow();
      await expect(deleteServer('server')).rejects.toThrow();
      await expect(initiateOAuth('server')).rejects.toThrow();
    });
    expect(mocks.post).not.toHaveBeenCalled();
    expect(mocks.delete).not.toHaveBeenCalled();
  });
});
