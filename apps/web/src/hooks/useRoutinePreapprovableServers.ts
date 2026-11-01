/**
 * The MCP servers a routine's form may pre-approve, for the account in session
 * (spec 2026-10-29 D9): the account's own servers and the administrator's, read
 * through their own hooks, kept to what a routine's runs can call.
 */
import { useMemo } from 'react';

import { useAdminMCPServers } from '@/hooks/useAdminMCPServers';
import { useUserMCPServers } from '@/hooks/useUserMCPServers';
import {
  preapprovableServers,
  type PreapprovableServer,
} from '@/lib/routines/preapprovable-servers';

export function useRoutinePreapprovableServers(): PreapprovableServer[] {
  const { servers: personal } = useUserMCPServers();
  const { servers: shared } = useAdminMCPServers();
  return useMemo(() => preapprovableServers(personal, shared), [personal, shared]);
}
