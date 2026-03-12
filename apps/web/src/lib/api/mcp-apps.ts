/**
 * MCP Apps API Client — Proxy calls from MCP App iframes to backend MCP servers.
 *
 * Routes requests based on server_source:
 * - user  -> POST /api/v1/mcp/servers/{server_id}/app/...
 * - admin -> POST /api/v1/mcp/admin-servers/{server_key}/app/...
 *
 * Phase: evolution F2.5 — MCP Apps
 */

import { API_URL } from '@/lib/api-config';
import type { McpAppRegistryPayload } from '@/types/mcp-apps';

function getBasePath(payload: McpAppRegistryPayload): string {
  if (payload.server_source === 'admin') {
    return `${API_URL}/mcp/admin-servers/${encodeURIComponent(payload.server_key)}`;
  }
  return `${API_URL}/mcp/servers/${encodeURIComponent(payload.server_id)}`;
}

export async function mcpAppCallTool(
  payload: McpAppRegistryPayload,
  toolName: string,
  args: Record<string, unknown>,
): Promise<{ success: boolean; result?: string; error?: string }> {
  const basePath = getBasePath(payload);
  const response = await fetch(`${basePath}/app/call-tool`, {
    method: 'POST',
    credentials: 'include',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ tool_name: toolName, arguments: args }),
  });
  if (!response.ok) {
    return { success: false, error: `HTTP ${response.status}: ${response.statusText}` };
  }
  return response.json();
}

export async function mcpAppReadResource(
  payload: McpAppRegistryPayload,
  uri: string,
): Promise<{ success: boolean; content?: string; mime_type?: string; error?: string }> {
  const basePath = getBasePath(payload);
  const response = await fetch(`${basePath}/app/read-resource`, {
    method: 'POST',
    credentials: 'include',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ uri }),
  });
  if (!response.ok) {
    return { success: false, error: `HTTP ${response.status}: ${response.statusText}` };
  }
  return response.json();
}
