/**
 * Hook for fetching and toggling admin-configured MCP servers.
 *
 * Admin MCP servers are configured globally in MCP_SERVERS_CONFIG (.env).
 * Users can toggle individual servers on/off via their admin_mcp_disabled_servers list.
 *
 * Phase: evolution F2.5 — Admin MCP Per-Server Routing & User Toggle
 * Created: 2026-03-03
 */
import { useCallback, useRef } from 'react';
import { useApplicationAccountQuery } from '@/hooks/useApplicationAccountQuery';
import { useApplicationAccountLifetime } from '@/hooks/useApplicationAccountLifetime';
import { useApplicationResourceSync } from '@/hooks/useApplicationResourceSync';
import { useApiMutation } from '@/hooks/useApiMutation';
import { useTranslation } from 'react-i18next';
import { toast } from 'sonner';

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

export interface AdminMCPToolInfo {
  name: string;
  description: string | null;
  /** Display name the server declares; null means fall back to `name`. */
  title?: string | null;
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
    ownerId,
  } = useApplicationAccountQuery<AdminMCPServer[]>(ENDPOINT, COMPONENT_NAME);
  const { isCurrent } = useApplicationAccountLifetime(ownerId);
  const { t } = useTranslation();
  const release = useCallback(() => {}, []);
  useApplicationResourceSync(ownerId, 'shared_mcp_preferences', refetch, release);
  const queues = useRef(new Map<string, Promise<AdminMCPToggleResponse | undefined>>());

  const { mutate: toggleMutate, loading: toggling } = useApiMutation<
    undefined,
    AdminMCPToggleResponse
  >({
    method: 'PATCH',
    componentName: COMPONENT_NAME,
  });

  const toggleServer = useCallback(
    (serverKey: string) => {
      const previous = queues.current.get(serverKey) ?? Promise.resolve(undefined);
      const pending = previous.catch(() => undefined).then(async () => {
        if (!isCurrent()) return undefined;
        const result = await toggleMutate(`${ENDPOINT}/${encodeURIComponent(serverKey)}/toggle`, undefined);
        if (!isCurrent()) return undefined;
        if (result) {
          try { await refetch(); }
          catch { if (isCurrent()) toast.error(t('settings.application_tools.sync_failed')); }
        }
        return isCurrent() ? result : undefined;
      });
      queues.current.set(serverKey, pending);
      void pending.finally(() => {
        if (queues.current.get(serverKey) === pending) queues.current.delete(serverKey);
      }).catch(() => {});
      return pending;
    },
    [toggleMutate, isCurrent, refetch, t]
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
