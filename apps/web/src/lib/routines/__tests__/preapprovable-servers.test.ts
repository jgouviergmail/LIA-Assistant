/**
 * A routine may pre-approve exactly the MCP servers its runs can call (spec D9).
 *
 * The form lists them and the REST route accepts them: the account's own servers,
 * enabled and active, by id; the administrator's servers the account has not
 * switched off, by key — the keys a tool manifest names its server by.
 */
import { describe, expect, it } from 'vitest';

import type { AdminMCPServer } from '@/hooks/useAdminMCPServers';
import type { UserMCPServer } from '@/hooks/useUserMCPServers';
import { callableSelection, preapprovableServers } from '@/lib/routines/preapprovable-servers';

function personal(over: Partial<UserMCPServer>): UserMCPServer {
  return {
    id: 'p-1',
    name: 'Notes',
    url: 'https://notes.example.com/mcp',
    plugin_id: null,
    auth_type: 'none',
    status: 'active',
    is_enabled: true,
    domain_description: null,
    timeout_seconds: 30,
    hitl_required: null,
    iterative_mode: false,
    ...over,
  } as UserMCPServer;
}

function shared(over: Partial<AdminMCPServer>): AdminMCPServer {
  return {
    server_key: 'excalidraw',
    name: 'Excalidraw',
    description: null,
    tools_count: 1,
    tools: [],
    enabled_for_user: true,
    ...over,
  } as AdminMCPServer;
}

describe('preapprovableServers', () => {
  it('test_form_lists_exactly_what_the_routine_can_call', () => {
    const servers = preapprovableServers(
      [
        personal({ id: 'p-on', name: 'Notes' }),
        personal({ id: 'p-off', name: 'Off', is_enabled: false }),
        personal({ id: 'p-auth', name: 'Auth', status: 'auth_required' }),
      ],
      [
        shared({ server_key: 'excalidraw', name: 'Excalidraw' }),
        shared({ server_key: 'switched-off', name: 'Off', enabled_for_user: false }),
      ]
    );

    expect(servers).toEqual([
      { key: 'p-on', name: 'Notes', family: 'personal' },
      { key: 'excalidraw', name: 'Excalidraw', family: 'shared' },
    ]);
  });
});

describe('callableSelection', () => {
  it('keeps the ticks of servers still callable and drops a stale key', () => {
    const servers = [{ key: 'p-on', name: 'Notes', family: 'personal' as const }];

    expect(callableSelection(['gone', 'p-on'], servers)).toEqual(['p-on']);
  });
});
