/**
 * The MCP servers a routine's form may pre-approve, for the account in session
 * (spec 2026-10-29 D9): the account's own servers and the administrator's, read
 * through their own hooks, kept to what a routine's runs can call.
 *
 * The personal servers' router refuses every route under the operator's switch
 * (ADR-280): the form asks it only where the instance offers them. The
 * administrator's servers answer from a router that switch does not close.
 */
import { useMemo } from 'react';

import { useAdminMCPServers } from '@/hooks/useAdminMCPServers';
import { useAppConfig } from '@/hooks/useAppConfig';
import { useUserMCPServers } from '@/hooks/useUserMCPServers';
import { capabilityAvailable } from '@/lib/capability-availability';
import {
  preapprovableServers,
  type PreapprovableServer,
} from '@/lib/routines/preapprovable-servers';

export function useRoutinePreapprovableServers(): PreapprovableServer[] {
  const { config } = useAppConfig();
  const { servers: personal } = useUserMCPServers(capabilityAvailable(config, 'mcp'));
  const { servers: shared } = useAdminMCPServers();
  return useMemo(() => preapprovableServers(personal, shared), [personal, shared]);
}
