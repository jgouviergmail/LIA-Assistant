/**
 * Hook for fetching and toggling admin-configured MCP servers.
 *
 * Admin MCP servers are configured globally in MCP_SERVERS_CONFIG (.env).
 * Users can toggle individual servers on/off via their admin_mcp_disabled_servers list.
 *
 * Phase: evolution F2.5 — Admin MCP Per-Server Routing & User Toggle
 * Created: 2026-03-03
 */
import { useCallback } from 'react';
import { useApiQuery } from '@/hooks/useApiQuery';
import { useApiMutation } from '@/hooks/useApiMutation';

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

export interface AdminMCPToolInfo {
  name: string;
  description: string | null;
}

export interface AdminMCPServer {
  server_key: string;
  name: string;
  description: string | null;
  tools_count: number;
  tools: AdminMCPToolInfo[];
  enabled_for_user: boolean;
}

interface AdminMCPToggleResponse {
  server_key: string;
  enabled_for_user: boolean;
}

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

const ENDPOINT = '/mcp/admin-servers';
const COMPONENT_NAME = 'useAdminMCPServers';

// ---------------------------------------------------------------------------
// Hook
// ---------------------------------------------------------------------------

export function useAdminMCPServers() {
  const {
    data: servers,
    loading,
    error,
    refetch,
    setData,
  } = useApiQuery<AdminMCPServer[]>(ENDPOINT, {
    componentName: COMPONENT_NAME,
    initialData: [],
  });

  const { mutate: toggleMutate, loading: toggling } = useApiMutation<
    undefined,
    AdminMCPToggleResponse
  >({
    method: 'PATCH',
    componentName: COMPONENT_NAME,
    onSuccess: result => {
      // Optimistic update: toggle the server in local cache
      setData(prev =>
        (prev ?? []).map(s =>
          s.server_key === result.server_key
            ? { ...s, enabled_for_user: result.enabled_for_user }
            : s
        )
      );
    },
  });

  const toggleServer = useCallback(
    (serverKey: string) => toggleMutate(`${ENDPOINT}/${serverKey}/toggle`, undefined),
    [toggleMutate]
  );

  return {
    servers: servers ?? [],
    loading,
    error,
    refetch,
    toggleServer,
    toggling,
  };
}
