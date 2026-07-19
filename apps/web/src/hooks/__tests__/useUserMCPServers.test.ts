/**
 * useUserMCPServers — the CRUD layer for the user's own MCP servers, mocked out
 * by the settings-panel tests and therefore only pinned here.
 *
 * Beyond the usual optimistic updaters, two operations are not plain writes and
 * carry their own rule: a **successful** connection test refetches (the server
 * cached a new tool list, so the local copy is stale), and an OAuth initiation
 * hands the browser over — but only when the server actually returned a URL.
 */

import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';

import { renderHook, act } from '@/__tests__/test-utils';
import {
  mutateSpy,
  mutationResult,
  queryResult,
  setDataSpy,
  takeUpdater,
} from '@/__tests__/api-mocks';

const { useApiQuery } = vi.hoisted(() => ({ useApiQuery: vi.fn() }));
vi.mock('@/hooks/useApiQuery', () => ({ useApiQuery }));
const { useApiMutation } = vi.hoisted(() => ({ useApiMutation: vi.fn() }));
vi.mock('@/hooks/useApiMutation', () => ({ useApiMutation }));

import { useUserMCPServers } from '../useUserMCPServers';
import type { UserMCPServer, UserMCPServerListResponse } from '@/hooks/useUserMCPServers';

const ENDPOINT = '/mcp/servers';

function server(over: Partial<UserMCPServer> = {}): UserMCPServer {
  return {
    id: 's1',
    name: 'Weather MCP',
    url: 'https://mcp.example.com/sse',
    auth_type: 'none',
    status: 'active',
    is_enabled: true,
    domain_description: null,
    timeout_seconds: 30,
    hitl_required: null,
    iterative_mode: false,
    header_name: null,
    has_credentials: false,
    has_oauth_credentials: false,
    oauth_scopes: null,
    tool_count: 2,
    tools: [],
    last_connected_at: null,
    last_error: null,
    created_at: '2026-01-01T00:00:00Z',
    updated_at: '2026-01-01T00:00:00Z',
    ...over,
  };
}

/** The eight mutations, in the order the hook declares them. */
const mutate = {
  create: mutateSpy(),
  update: mutateSpy(),
  remove: mutateSpy(),
  toggle: mutateSpy(),
  test: mutateSpy(),
  oauth: mutateSpy(),
  oauthDisconnect: mutateSpy(),
  describe: mutateSpy(),
};
const ORDER = [
  mutate.create,
  mutate.update,
  mutate.remove,
  mutate.toggle,
  mutate.test,
  mutate.oauth,
  mutate.oauthDisconnect,
  mutate.describe,
];

const setData = setDataSpy<UserMCPServerListResponse>();
const refetch = vi.fn();

function cache(over: Partial<UserMCPServerListResponse> = {}): UserMCPServerListResponse {
  return { servers: [server()], total: 1, ...over };
}

function setupWith(data: UserMCPServerListResponse | undefined) {
  useApiQuery.mockReturnValue(queryResult<UserMCPServerListResponse>({ data, setData, refetch }));
  return renderHook(() => useUserMCPServers());
}

const setup = (data: UserMCPServerListResponse = cache()) => setupWith(data);

function applyUpdater(previous: UserMCPServerListResponse | undefined) {
  return takeUpdater<UserMCPServerListResponse>(setData)(previous);
}

let originalLocation: Location;

beforeEach(() => {
  vi.clearAllMocks();
  let cursor = 0;
  useApiMutation.mockImplementation(() =>
    mutationResult({ mutate: ORDER[cursor++ % ORDER.length] })
  );
  Object.values(mutate).forEach(m => m.mockResolvedValue(undefined));
  originalLocation = window.location;
  Object.defineProperty(window, 'location', {
    value: { href: '' },
    writable: true,
    configurable: true,
  });
});

afterEach(() => {
  Object.defineProperty(window, 'location', { value: originalLocation, configurable: true });
});

describe('useUserMCPServers — reading', () => {
  it('reads the collection and exposes it', () => {
    const { result } = setup();

    expect(useApiQuery).toHaveBeenCalledWith(ENDPOINT, expect.objectContaining({}));
    expect(result.current.servers).toHaveLength(1);
    expect(result.current.total).toBe(1);
  });

  it('degrades to an empty list on a missing payload', () => {
    const { result } = setupWith(undefined);

    expect(result.current.servers).toEqual([]);
    expect(result.current.total).toBe(0);
  });
});

describe('useUserMCPServers — writing', () => {
  const draft = { name: 'New', url: 'https://x/sse', auth_type: 'none' as const };

  it('appends a created server and counts it', async () => {
    const created = server({ id: 's2', name: 'New' });
    mutate.create.mockResolvedValue(created);
    const { result } = setup();

    await act(async () => {
      await result.current.createServer(draft);
    });

    expect(mutate.create).toHaveBeenCalledWith(ENDPOINT, draft);
    expect(applyUpdater(cache())).toEqual({ servers: [server(), created], total: 2 });
  });

  it('replaces only the updated server', async () => {
    const updated = server({ name: 'Renamed' });
    mutate.update.mockResolvedValue(updated);
    const { result } = setup();

    await act(async () => {
      await result.current.updateServer('s1', { name: 'Renamed' });
    });

    expect(mutate.update).toHaveBeenCalledWith(`${ENDPOINT}/s1`, { name: 'Renamed' });
    const next = applyUpdater(cache({ servers: [server(), server({ id: 's2' })], total: 2 }));
    expect(next?.servers).toEqual([updated, server({ id: 's2' })]);
  });

  it('removes a deleted server and decrements the count', async () => {
    const { result } = setup();

    await act(async () => {
      await result.current.deleteServer('s1');
    });

    expect(mutate.remove).toHaveBeenCalledWith(`${ENDPOINT}/s1`);
    expect(applyUpdater(cache({ servers: [server(), server({ id: 's2' })], total: 2 }))).toEqual({
      servers: [server({ id: 's2' })],
      total: 1,
    });
  });

  it('swaps the server in after a toggle', async () => {
    const toggled = server({ is_enabled: false });
    mutate.toggle.mockResolvedValue(toggled);
    const { result } = setup();

    await act(async () => {
      await result.current.toggleServer('s1');
    });

    expect(mutate.toggle).toHaveBeenCalledWith(`${ENDPOINT}/s1/toggle`);
    expect(applyUpdater(cache())?.servers).toEqual([toggled]);
  });

  it.each([
    ['create', (h: ReturnType<typeof useUserMCPServers>) => h.createServer(draft)],
    ['update', (h: ReturnType<typeof useUserMCPServers>) => h.updateServer('s1', { name: 'x' })],
    ['toggle', (h: ReturnType<typeof useUserMCPServers>) => h.toggleServer('s1')],
  ])('writes nothing when %s is refused', async (_label, run) => {
    const { result } = setup();

    await act(async () => {
      await run(result.current);
    });

    expect(setData).not.toHaveBeenCalled();
  });
});

describe('useUserMCPServers — connection test', () => {
  it('refreshes the list when the handshake succeeds', async () => {
    mutate.test.mockResolvedValue({ success: true, tool_count: 4, tools: [] });
    const { result } = setup();

    await act(async () => {
      await result.current.testConnection('s1');
    });

    expect(mutate.test).toHaveBeenCalledWith(`${ENDPOINT}/s1/test`);
    // The server just refreshed its tool cache: the local copy is stale.
    expect(refetch).toHaveBeenCalledTimes(1);
  });

  it('leaves the list alone when the handshake fails', async () => {
    mutate.test.mockResolvedValue({ success: false, tool_count: 0, tools: [], error: 'refused' });
    const { result } = setup();

    await act(async () => {
      await result.current.testConnection('s1');
    });

    expect(refetch).not.toHaveBeenCalled();
  });
});

describe('useUserMCPServers — OAuth', () => {
  it('hands the browser over to the authorization server', async () => {
    mutate.oauth.mockResolvedValue({ authorization_url: 'https://auth.example/oauth' });
    const { result } = setup();

    await act(async () => {
      await result.current.initiateOAuth('s1');
    });

    expect(mutate.oauth).toHaveBeenCalledWith(`${ENDPOINT}/s1/oauth/authorize`);
    expect(window.location.href).toBe('https://auth.example/oauth');
  });

  it('stays put when no authorization URL comes back', async () => {
    mutate.oauth.mockResolvedValue({ authorization_url: '' });
    const { result } = setup();

    await act(async () => {
      await result.current.initiateOAuth('s1');
    });

    expect(window.location.href).toBe('');
  });

  it('swaps the disconnected server back in', async () => {
    const disconnected = server({ has_oauth_credentials: false });
    mutate.oauthDisconnect.mockResolvedValue(disconnected);
    const { result } = setup();

    await act(async () => {
      await result.current.disconnectOAuth('s1');
    });

    expect(mutate.oauthDisconnect).toHaveBeenCalledWith(`${ENDPOINT}/s1/oauth/disconnect`);
    expect(applyUpdater(cache())?.servers).toEqual([disconnected]);
  });
});

describe('useUserMCPServers — generated description', () => {
  it('writes the generated description onto the server, keeping the rest', async () => {
    mutate.describe.mockResolvedValue({ domain_description: 'Weather and forecasts' });
    const { result } = setup();

    await act(async () => {
      await result.current.generateDescription('s1');
    });

    expect(mutate.describe).toHaveBeenCalledWith(`${ENDPOINT}/s1/generate-description`);
    const next = applyUpdater(cache());
    expect(next?.servers[0]).toEqual(server({ domain_description: 'Weather and forecasts' }));
  });

  it('leaves the server untouched when nothing was generated', async () => {
    const { result } = setup();

    await act(async () => {
      await result.current.generateDescription('s1');
    });

    expect(setData).not.toHaveBeenCalled();
  });
});

describe('useUserMCPServers — updaters on an empty cache', () => {
  it.each([
    [
      'create',
      (h: ReturnType<typeof useUserMCPServers>) =>
        h.createServer({ name: 'n', url: 'u', auth_type: 'none' as const }),
    ],
    ['update', (h: ReturnType<typeof useUserMCPServers>) => h.updateServer('s1', { name: 'n' })],
    ['delete', (h: ReturnType<typeof useUserMCPServers>) => h.deleteServer('s1')],
    ['toggle', (h: ReturnType<typeof useUserMCPServers>) => h.toggleServer('s1')],
    ['disconnect', (h: ReturnType<typeof useUserMCPServers>) => h.disconnectOAuth('s1')],
    ['describe', (h: ReturnType<typeof useUserMCPServers>) => h.generateDescription('s1')],
  ])('%s leaves an empty cache untouched', async (_label, run) => {
    Object.values(mutate).forEach(m =>
      m.mockResolvedValue({ ...server(), domain_description: 'd' })
    );
    const { result } = setup();

    await act(async () => {
      await run(result.current);
    });

    expect(applyUpdater(undefined)).toBeUndefined();
  });
});
