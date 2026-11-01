/**
 * The MCP servers a routine may pre-approve (spec 2026-10-29 D9).
 *
 * A routine runs with nobody to ask, so LIA refuses the MCP tools that need a
 * confirmation. The routine's form may tick the servers whose confirmations its
 * runs give themselves — exactly the servers those runs can call, keyed the way a
 * tool names its server: the person's own servers, enabled and active, by id; the
 * administrator's servers they have not switched off, by key. The API accepts
 * exactly these and refuses anything else.
 */
import type { AdminMCPServer } from '@/hooks/useAdminMCPServers';
import type { UserMCPServer } from '@/hooks/useUserMCPServers';

/** One server the routine may pre-approve. */
export interface PreapprovableServer {
  /** How a tool names its server: a personal server's id, an administrator server's key. */
  key: string;
  name: string;
  family: 'personal' | 'shared';
}

/**
 * Every server a routine's runs can call, personal first.
 *
 * @param personal - The account's own MCP servers.
 * @param shared - The administrator's MCP servers, with the account's switch.
 * @returns The servers a pre-approval may name, in display order.
 */
export function preapprovableServers(
  personal: readonly UserMCPServer[],
  shared: readonly AdminMCPServer[]
): PreapprovableServer[] {
  return [
    ...personal
      .filter(server => server.is_enabled && server.status === 'active')
      .map(server => ({ key: server.id, name: server.name, family: 'personal' as const })),
    ...shared
      .filter(server => server.enabled_for_user)
      .map(server => ({ key: server.server_key, name: server.name, family: 'shared' as const })),
  ];
}

/**
 * The ticks a change keeps: only servers still callable.
 *
 * A key stored before its server was removed or switched off is read as it is
 * — and dropped the moment the person changes the selection, so the saved list
 * is one the API accepts.
 *
 * @param next - The ticked keys after the change.
 * @param servers - The servers the routine can call now.
 * @returns The keys to save.
 */
export function callableSelection(
  next: readonly string[],
  servers: readonly PreapprovableServer[]
): string[] {
  const callable = new Set(servers.map(server => server.key));
  return next.filter(key => callable.has(key));
}
