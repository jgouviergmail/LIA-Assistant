import type { UserMCPServer } from '@/hooks/useUserMCPServers';

/** One saved personal MCP server, active, driven directly, with no choice of its own. */
export function userMCPServerFixture(overrides: Partial<UserMCPServer> = {}): UserMCPServer {
  return {
    id: 's1',
    name: 'Weather MCP',
    url: 'https://mcp.example.com/sse',
    plugin_id: null,
    auth_type: 'none',
    status: 'active',
    is_enabled: true,
    domain_description: null,
    timeout_seconds: 30,
    hitl_required: null,
    iterative_mode: false,
    react_expand_iterative: null,
    suspended_tool_choices: 0,
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
    ...overrides,
  };
}
