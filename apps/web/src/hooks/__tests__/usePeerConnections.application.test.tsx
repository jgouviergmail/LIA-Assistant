import { act, renderHook, waitFor } from '@testing-library/react';
import { beforeEach, expect, it, vi } from 'vitest';

const { useAuth, get, put, post, del } = vi.hoisted(() => ({
  useAuth: vi.fn(),
  get: vi.fn(),
  put: vi.fn(),
  post: vi.fn(),
  del: vi.fn(),
}));
vi.mock('@/hooks/useAuth', () => ({ useAuth }));
vi.mock('@/lib/api-client', async importOriginal => ({
  ...(await importOriginal<typeof import('@/lib/api-client')>()),
  default: { get, put, post, delete: del },
  apiClient: { get, put, post, delete: del },
}));
import { usePeerConnections } from '../usePeerConnections';
import { publishApplicationResources } from '@/lib/application-resources';

beforeEach(() => {
  vi.clearAllMocks();
  get.mockReset();
  useAuth.mockReturnValue({ user: { id: 'one' } });
  get.mockImplementation(async (url: string) =>
    url === '/peers/me' ? { discovery_enabled: false, email_visible: false } : []
  );
});

it('rereads source consent after the current account native peers hint', async () => {
  const { result } = renderHook(() => usePeerConnections());
  await waitFor(() => expect(result.current.emailVisible).toBe(false));
  get.mockImplementation(async (url: string) =>
    url === '/peers/me' ? { discovery_enabled: false, email_visible: true } : []
  );
  act(() => publishApplicationResources('one', new Set(['peers'])));
  await waitFor(() => expect(result.current.emailVisible).toBe(true));
});

it('hides old account connection cards and refuses its obsolete write callback', async () => {
  get.mockImplementation(async (url: string) =>
    url === '/peers/connections'
      ? [{ id: 'private-connection', peer_display_name: 'Private Alice' }]
      : url === '/peers/me'
        ? { discovery_enabled: true, email_visible: true }
        : []
  );
  const { result, rerender } = renderHook(() => usePeerConnections());
  await waitFor(() => expect(result.current.connections).toHaveLength(1));
  const obsolete = result.current.setEmailVisible;
  useAuth.mockReturnValue({ user: { id: 'two' } });
  get.mockImplementation(() => new Promise(() => {}));
  rerender();
  expect(result.current.connections).toEqual([]);
  expect(result.current.emailVisible).toBeNull();
  await act(async () => {
    await obsolete(false);
  });
  expect(put).not.toHaveBeenCalled();
});
