import { useCallback } from 'react';
import { useApplicationAccountQuery } from './useApplicationAccountQuery';
import { useApplicationResourceSync } from './useApplicationResourceSync';
import { useApiMutation } from './useApiMutation';
import type { UserMCPDefaults } from '@/lib/mcp-behavior';
import { navigateToAuthorizationUrl } from '@/lib/safe-navigation';

/**
 * Auth type for a user MCP server.
 */
export type UserMCPAuthType = 'none' | 'api_key' | 'bearer' | 'oauth2';

/**
 * Server status.
 */
export type UserMCPServerStatus = 'active' | 'inactive' | 'auth_required' | 'error';

/**
 * Discovered tool from an MCP server.
 */
export interface MCPDiscoveredTool {
  tool_name: string;
  description: string;
  input_schema: Record<string, unknown>;
  /**
   * Display name the server declares. The MCP spec fixes the precedence
   * (`title`, then `annotations.title`, then `name`), so the backend sends the
   * first two and a null here means "fall back to tool_name".
   */
  title?: string | null;
}

/**
 * User MCP server from the API.
 */
export interface UserMCPServer {
  shared_origin?: import('@/lib/capability-sharing').CapabilityOrigin | null;
  /** Sender side: the connections this item was shared with (newest share each). */
  shared_with?: import('@/lib/capability-sharing').CapabilityShare[];
  id: string;
  name: string;
  url: string;
  /** Agent Plugins provenance (ADR-225); non-null = uninstall via the plugin. */
  plugin_id: string | null;
  auth_type: UserMCPAuthType;
  status: UserMCPServerStatus;
  is_enabled: boolean;
  domain_description: string | null;
  timeout_seconds: number;
  hitl_required: boolean | null;
  iterative_mode: boolean;
  /** ReAct shape of an iterative server; null follows the instance default. */
  react_expand_iterative: boolean | null;
  /** Tools whose « never ask » the server's new declaration suspended (spec D6). */
  suspended_tool_choices: number;
  header_name: string | null;
  has_credentials: boolean;
  has_oauth_credentials: boolean;
  oauth_scopes: string | null;
  tool_count: number;
  tools: MCPDiscoveredTool[];
  last_connected_at: string | null;
  last_error: string | null;
  created_at: string;
  updated_at: string;
}

/**
 * Create payload.
 */
export interface UserMCPServerCreate {
  name: string;
  url: string;
  auth_type: UserMCPAuthType;
  api_key?: string;
  header_name?: string;
  bearer_token?: string;
  oauth_client_id?: string;
  oauth_client_secret?: string;
  oauth_scopes?: string;
  domain_description?: string;
  timeout_seconds?: number;
  hitl_required?: boolean | null;
  iterative_mode?: boolean;
  react_expand_iterative?: boolean | null;
}

/**
 * Update payload (partial).
 */
export interface UserMCPServerUpdate {
  name?: string;
  url?: string;
  auth_type?: UserMCPAuthType;
  api_key?: string;
  header_name?: string;
  bearer_token?: string;
  oauth_client_id?: string;
  oauth_client_secret?: string;
  oauth_scopes?: string;
  domain_description?: string | null;
  timeout_seconds?: number;
  hitl_required?: boolean | null;
  iterative_mode?: boolean;
  react_expand_iterative?: boolean | null;
}

/**
 * Test connection response.
 */
/** Why a test did not succeed, when the remedy is stated in the person's language. */
export type MCPTestErrorCode = 'oauth_authorization_required';

export interface TestConnectionResponse {
  success: boolean;
  tool_count: number;
  tools: MCPDiscoveredTool[];
  error: string | null;
  /** Absent on older answers; set when the failure has a remedy (an authorization). */
  error_code?: MCPTestErrorCode | null;
  domain_description: string | null;
}

/**
 * Generate description response.
 */
export interface GenerateDescriptionResponse {
  domain_description: string;
  tool_count: number;
}

/**
 * OAuth initiation response.
 */
export interface OAuthInitiateResponse {
  authorization_url: string;
}

/**
 * API list response shape.
 */
export interface UserMCPServerListResponse {
  servers: UserMCPServer[];
  total: number;
  /** What a choice left open inherits (spec 2026-10-30 D2). */
  defaults: UserMCPDefaults;
}

const ENDPOINT = '/mcp/servers';

/**
 * Hook for user MCP servers CRUD operations.
 *
 * @param enabled - Whether the instance offers the personal servers now. Their
 *   router refuses every route under the operator's switch (ADR-280): a caller
 *   that mounts outside their own section — a routine's form — says so, and
 *   nothing is asked.
 */
export function useUserMCPServers(enabled = true) {
  // Query: list all
  const {
    data: listData,
    loading,
    error,
    refetch,
    setData,
    ownerId,
    isCurrent,
  } = useApplicationAccountQuery<UserMCPServerListResponse>(ENDPOINT, 'UserMCPServers', enabled);
  useApplicationResourceSync(ownerId, 'user_mcp', refetch);

  const inAccount = useCallback(
    async <T>(perform: () => Promise<T>) => {
      if (!isCurrent()) throw new Error('Application account changed');
      const result = await perform();
      return isCurrent() ? result : undefined;
    },
    [isCurrent]
  );

  const servers = listData?.servers ?? [];
  const total = listData?.total ?? 0;

  // Mutations
  const createMutation = useApiMutation<UserMCPServerCreate, UserMCPServer>({
    method: 'POST',
    componentName: 'UserMCPServers',
  });

  const updateMutation = useApiMutation<UserMCPServerUpdate, UserMCPServer>({
    method: 'PATCH',
    componentName: 'UserMCPServers',
  });

  const deleteMutation = useApiMutation<void, void>({
    method: 'DELETE',
    componentName: 'UserMCPServers',
  });

  const toggleMutation = useApiMutation<void, UserMCPServer>({
    method: 'PATCH',
    componentName: 'UserMCPServers',
  });

  const testMutation = useApiMutation<void, TestConnectionResponse>({
    method: 'POST',
    componentName: 'UserMCPServers',
  });

  const oauthMutation = useApiMutation<void, OAuthInitiateResponse>({
    method: 'POST',
    componentName: 'UserMCPServers',
  });

  const oauthDisconnectMutation = useApiMutation<void, UserMCPServer>({
    method: 'POST',
    componentName: 'UserMCPServers',
  });

  const generateDescriptionMutation = useApiMutation<void, GenerateDescriptionResponse>({
    method: 'POST',
    componentName: 'UserMCPServers',
  });

  // Handlers
  const createServer = useCallback(
    async (data: UserMCPServerCreate) => {
      const result = await inAccount(() => createMutation.mutate(ENDPOINT, data));
      if (result) {
        setData(prev => {
          if (!prev) return prev;
          return {
            ...prev,
            servers: [...prev.servers, result],
            total: prev.total + 1,
          };
        });
      }
      return result;
    },
    [inAccount, createMutation, setData]
  );

  const updateServer = useCallback(
    async (serverId: string, data: UserMCPServerUpdate) => {
      const result = await inAccount(() => updateMutation.mutate(`${ENDPOINT}/${serverId}`, data));
      if (result) {
        setData(prev => {
          if (!prev) return prev;
          return {
            ...prev,
            servers: prev.servers.map(s => (s.id === serverId ? result : s)),
          };
        });
      }
      return result;
    },
    [inAccount, updateMutation, setData]
  );

  const deleteServer = useCallback(
    async (serverId: string) => {
      await inAccount(() => deleteMutation.mutate(`${ENDPOINT}/${serverId}`));
      setData(prev => {
        if (!prev) return prev;
        return {
          ...prev,
          servers: prev.servers.filter(s => s.id !== serverId),
          total: prev.total - 1,
        };
      });
    },
    [inAccount, deleteMutation, setData]
  );

  const toggleServer = useCallback(
    async (serverId: string) => {
      const result = await inAccount(() => toggleMutation.mutate(`${ENDPOINT}/${serverId}/toggle`));
      if (result) {
        setData(prev => {
          if (!prev) return prev;
          return {
            ...prev,
            servers: prev.servers.map(s => (s.id === serverId ? result : s)),
          };
        });
      }
      return result;
    },
    [inAccount, toggleMutation, setData]
  );

  const testConnection = useCallback(
    async (serverId: string) => {
      const result = await inAccount(() => testMutation.mutate(`${ENDPOINT}/${serverId}/test`));
      if (result) {
        // Every answered test stored a status (and, on success, the tools): a failure
        // that left the server `auth_required` must offer its authorization at once.
        refetch();
      }
      return result;
    },
    [inAccount, testMutation, refetch]
  );

  const initiateOAuth = useCallback(
    async (serverId: string) => {
      const result = await inAccount(() =>
        oauthMutation.mutate(`${ENDPOINT}/${serverId}/oauth/authorize`)
      );
      if (result?.authorization_url) {
        // Redirect to OAuth authorization server
        navigateToAuthorizationUrl(result.authorization_url, 'mcp-oauth');
      }
      return result;
    },
    [inAccount, oauthMutation]
  );

  const disconnectOAuth = useCallback(
    async (serverId: string) => {
      const result = await inAccount(() =>
        oauthDisconnectMutation.mutate(`${ENDPOINT}/${serverId}/oauth/disconnect`)
      );
      if (result) {
        setData(prev => {
          if (!prev) return prev;
          return {
            ...prev,
            servers: prev.servers.map(s => (s.id === serverId ? result : s)),
          };
        });
      }
      return result;
    },
    [inAccount, oauthDisconnectMutation, setData]
  );

  const generateDescription = useCallback(
    async (serverId: string) => {
      const result = await inAccount(() =>
        generateDescriptionMutation.mutate(`${ENDPOINT}/${serverId}/generate-description`)
      );
      if (result) {
        // Update server in local state with new description
        setData(prev => {
          if (!prev) return prev;
          return {
            ...prev,
            servers: prev.servers.map(s =>
              s.id === serverId ? { ...s, domain_description: result.domain_description } : s
            ),
          };
        });
      }
      return result;
    },
    [inAccount, generateDescriptionMutation, setData]
  );

  return {
    ownerId,
    // Data
    servers,
    total,
    defaults: listData?.defaults,
    loading,
    error,
    refetch,

    // Mutations
    createServer,
    updateServer,
    deleteServer,
    toggleServer,
    testConnection,
    initiateOAuth,
    disconnectOAuth,
    generateDescription,

    // Mutation states
    creating: createMutation.loading,
    updating: updateMutation.loading,
    deleting: deleteMutation.loading,
    toggling: toggleMutation.loading,
    testing: testMutation.loading,
    disconnecting: oauthDisconnectMutation.loading,
    generatingDescription: generateDescriptionMutation.loading,
  };
}
