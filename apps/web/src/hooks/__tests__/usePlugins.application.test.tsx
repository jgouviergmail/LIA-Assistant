import { act, renderHook, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { usePlugins, type InstalledPlugin } from '../usePlugins';
import { publishApplicationResources } from '@/lib/application-resources';

const mocks = vi.hoisted(() => ({ auth: vi.fn(), get: vi.fn(), post: vi.fn(), delete: vi.fn() }));
vi.mock('@/hooks/useAuth', () => ({ useAuth: mocks.auth }));
vi.mock('@/lib/api-client', async () => ({
  ...(await vi.importActual<typeof import('@/lib/api-client')>('@/lib/api-client')),
  default: { get: mocks.get, post: mocks.post, delete: mocks.delete },
}));
const plugin: InstalledPlugin = {
  id: 'plugin',
  name: 'private-plugin',
  version: '1',
  description: 'private metadata',
  spec_version: '1.0.0',
  skill_names: ['private-skill'],
  server_names: ['private-server'],
  created_at: null,
  updated_at: null,
};

beforeEach(() => {
  mocks.auth.mockReturnValue({ user: { id: 'owner' } });
  mocks.get.mockReset().mockResolvedValue({ plugins: [plugin], total: 1 });
  mocks.post.mockReset();
  mocks.delete.mockReset();
});

describe('personal plugin account and resource scope', () => {
  it('hides previous account metadata before the next response', async () => {
    const { result, rerender } = renderHook(() => usePlugins());
    await waitFor(() => expect(result.current.plugins[0]?.name).toBe(plugin.name));
    mocks.get.mockImplementation(() => new Promise(() => {}));
    mocks.auth.mockReturnValue({ user: { id: 'other' } });
    rerender();
    expect(result.current.plugins).toEqual([]);
  });

  it('refreshes the original plugin list on an owned plugin change only', async () => {
    const { result } = renderHook(() => usePlugins());
    await waitFor(() => expect(result.current.total).toBe(1));
    act(() => publishApplicationResources('other', new Set(['plugins'])));
    expect(mocks.get).toHaveBeenCalledTimes(1);
    mocks.get.mockResolvedValue({ plugins: [], total: 0 });
    act(() => publishApplicationResources('owner', new Set(['plugins'])));
    await waitFor(() => expect(result.current.total).toBe(0));
  });

  it('rejects retained previous-account mutation callbacks before any request', async () => {
    const { result, rerender } = renderHook(() => usePlugins());
    const { importFromUrl, importPlugin, uninstallPlugin } = result.current;
    mocks.auth.mockReturnValue({ user: { id: 'other' } });
    rerender();
    await act(async () => {
      await expect(importFromUrl('https://example.com/plugin.zip')).rejects.toThrow();
      await expect(importPlugin(new File(['zip'], 'plugin.zip'))).rejects.toThrow();
      await expect(uninstallPlugin('plugin')).rejects.toThrow();
    });
    expect(mocks.post).not.toHaveBeenCalled();
    expect(mocks.delete).not.toHaveBeenCalled();
  });
});
