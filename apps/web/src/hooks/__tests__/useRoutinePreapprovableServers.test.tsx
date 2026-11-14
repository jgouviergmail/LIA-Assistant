/**
 * The MCP servers a routine's form may pre-approve — and what it asks to know them.
 *
 * The personal servers' router refuses every route under the operator's switch
 * (ADR-280). The form used to ask it anyway, each time it opened, for an answer
 * that could only be a refusal. The administrator's servers answer from a
 * router the switch does not close: the form keeps reading and offering them.
 */
import { renderHook, waitFor } from '@testing-library/react';
import { act } from 'react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { appConfigFixture } from '@/__tests__/fixtures/app-config';
import { userMCPServerFixture } from '@/__tests__/fixtures/mcp-servers';
import type { AdminMCPServer } from '@/hooks/useAdminMCPServers';
import type { AppConfig } from '@/hooks/useAppConfig';

const mocks = vi.hoisted(() => ({
  get: vi.fn(),
  config: null as AppConfig | null,
}));
vi.mock('@/hooks/useAuth', () => ({ useAuth: () => ({ user: { id: 'owner' } }) }));
vi.mock('@/hooks/useAppConfig', () => ({ useAppConfig: () => ({ config: mocks.config }) }));
vi.mock('@/lib/api-client', async importOriginal => ({
  ...(await importOriginal<typeof import('@/lib/api-client')>()),
  default: { get: mocks.get },
}));

import { useRoutinePreapprovableServers } from '../useRoutinePreapprovableServers';

const PERSONAL = '/mcp/servers';
const SHARED = '/mcp/admin-servers';

const shared: AdminMCPServer = {
  server_key: 'instance-search',
  name: 'Instance search',
  description: null,
  tools_count: 1,
  tools: [],
  enabled_for_user: true,
};

/** A configuration that has answered, with the operator's verdict on the personal servers. */
const configWith = (enabled: boolean): AppConfig =>
  appConfigFixture({ capabilities: { mcp: { enabled, family: 'reach' } } });

const asked = () => mocks.get.mock.calls.map(([endpoint]) => String(endpoint));

/** Long enough for a deferred first read to leave, had one been queued. */
async function settle() {
  await act(async () => {
    await new Promise(resolve => setTimeout(resolve, 20));
  });
}

beforeEach(() => {
  mocks.get
    .mockReset()
    .mockImplementation(async (endpoint: string) =>
      endpoint === PERSONAL
        ? { servers: [userMCPServerFixture({ id: 'mine', name: 'My server' })], total: 1 }
        : [shared]
    );
  mocks.config = configWith(true);
});

describe('useRoutinePreapprovableServers', () => {
  it('offers the personal servers and the instance ones where both are readable', async () => {
    const { result } = renderHook(() => useRoutinePreapprovableServers());

    await waitFor(() => expect(result.current).toHaveLength(2));
    expect(result.current).toEqual([
      { key: 'mine', name: 'My server', family: 'personal' },
      { key: 'instance-search', name: 'Instance search', family: 'shared' },
    ]);
    expect(asked().sort()).toEqual([SHARED, PERSONAL].sort());
  });

  it('asks nothing of the personal router the operator closed, and keeps the instance servers', async () => {
    mocks.config = configWith(false);

    const { result } = renderHook(() => useRoutinePreapprovableServers());

    await waitFor(() => expect(result.current).toHaveLength(1));
    await settle();
    expect(result.current).toEqual([
      { key: 'instance-search', name: 'Instance search', family: 'shared' },
    ]);
    expect(asked()).toEqual([SHARED]);
  });

  it('waits for the configuration before it asks the personal router', async () => {
    // Before `/config` answers nobody knows whether the router is open: the
    // door says no, and the read leaves once it says yes.
    mocks.config = null;
    const { result, rerender } = renderHook(() => useRoutinePreapprovableServers());
    await settle();
    expect(asked()).toEqual([SHARED]);

    mocks.config = configWith(true);
    rerender();

    await waitFor(() => expect(result.current).toHaveLength(2));
    expect(asked().filter(endpoint => endpoint === PERSONAL)).toHaveLength(1);
  });
});
