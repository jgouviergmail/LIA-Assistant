/**
 * MCP Apps Types — Interactive widget registry payload and bridge protocol.
 *
 * Phase: evolution F2.5 — MCP Apps
 */

/** Payload stored in the Data Registry for MCP_APP items. */
export interface McpAppRegistryPayload {
  tool_name: string;
  server_name: string;
  html_content: string;
  tool_result: string;
  /** UUID string for user MCP servers, empty string for admin. */
  server_id: string;
  /** String key for admin MCP servers, empty string for user. */
  server_key: string;
  server_source: 'user' | 'admin';
  resource_uri: string;
  /** Original tool call arguments (for ui/notifications/tool-input). */
  tool_arguments: Record<string, unknown>;
  /** JSON Schema of the tool's input parameters (for hostContext.toolInfo). */
  tool_input_schema?: Record<string, unknown>;
}

/** JSON-RPC 2.0 message used in the postMessage bridge. */
export interface McpAppBridgeMessage {
  jsonrpc: '2.0';
  id?: string | number;
  method?: string;
  params?: Record<string, unknown>;
  result?: unknown;
  error?: { code: number; message: string; data?: unknown };
}
