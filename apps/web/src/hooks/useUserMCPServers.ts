import { useCallback } from 'react';
import { useApiQuery } from './useApiQuery';
import { useApiMutation } from './useApiMutation';

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
}

/**
 * User MCP server from the API.
 */
export interface UserMCPServer {
  id: string;
  name: string;
  url: string;
  auth_type: UserMCPAuthType;
  status: UserMCPServerStatus;
  is_enabled: boolean;
  domain_description: string | null;
  timeout_seconds: number;
  hitl_required: boolean | null;
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
  domain_description?: string;
  timeout_seconds?: number;
  hitl_required?: boolean | null;
}

/**
 * Test connection response.
 */
export interface TestConnectionResponse {
  success: boolean;
  tool_count: number;
  tools: MCPDiscoveredTool[];
  error: string | null;
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
interface UserMCPServerListResponse {
  servers: UserMCPServer[];
  total: number;
}

const ENDPOINT = '/mcp/servers';

/**
 * Hook for user MCP servers CRUD operations.
 */
export function useUserMCPServers() {
  // Query: list all
  const {
    data: listData,
    loading,
    error,
    refetch,
    setData,
  } = useApiQuery<UserMCPServerListResponse>(ENDPOINT, {
    componentName: 'UserMCPServers',
    initialData: { servers: [], total: 0 },
  });

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
      const result = await createMutation.mutate(ENDPOINT, data);
      if (result) {
        setData(prev => {
          if (!prev) return prev;
          return {
            servers: [...prev.servers, result],
            total: prev.total + 1,
          };
        });
      }
      return result;
    },
    [createMutation, setData]
  );

  const updateServer = useCallback(
    async (serverId: string, data: UserMCPServerUpdate) => {
      const result = await updateMutation.mutate(`${ENDPOINT}/${serverId}`, data);
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
    [updateMutation, setData]
  );

  const deleteServer = useCallback(
    async (serverId: string) => {
      await deleteMutation.mutate(`${ENDPOINT}/${serverId}`);
      setData(prev => {
        if (!prev) return prev;
        return {
          servers: prev.servers.filter(s => s.id !== serverId),
          total: prev.total - 1,
        };
      });
    },
    [deleteMutation, setData]
  );

  const toggleServer = useCallback(
    async (serverId: string) => {
      const result = await toggleMutation.mutate(`${ENDPOINT}/${serverId}/toggle`);
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
    [toggleMutation, setData]
  );

  const testConnection = useCallback(
    async (serverId: string) => {
      const result = await testMutation.mutate(`${ENDPOINT}/${serverId}/test`);
      if (result?.success) {
        // Refresh to get updated tools cache and status
        refetch();
      }
      return result;
    },
    [testMutation, refetch]
  );

  const initiateOAuth = useCallback(
    async (serverId: string) => {
      const result = await oauthMutation.mutate(`${ENDPOINT}/${serverId}/oauth/authorize`);
      if (result?.authorization_url) {
        // Redirect to OAuth authorization server
        window.location.href = result.authorization_url;
      }
      return result;
    },
    [oauthMutation]
  );

  const disconnectOAuth = useCallback(
    async (serverId: string) => {
      const result = await oauthDisconnectMutation.mutate(
        `${ENDPOINT}/${serverId}/oauth/disconnect`
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
    [oauthDisconnectMutation, setData]
  );

  const generateDescription = useCallback(
    async (serverId: string) => {
      const result = await generateDescriptionMutation.mutate(
        `${ENDPOINT}/${serverId}/generate-description`
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
    [generateDescriptionMutation, setData]
  );

  return {
    // Data
    servers,
    total,
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
