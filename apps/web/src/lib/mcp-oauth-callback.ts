/**
 * Resolution of the `mcp_oauth` callback marker appended by the backend
 * OAuth callback redirect (user MCP servers).
 *
 * Three outcomes exist on the wire: `success`, `denied` (the user refused
 * consent on the authorization server — not a system error) and `error`.
 * Any unknown value degrades to `error` because the URL is user-editable.
 */

export type McpOAuthOutcome = 'success' | 'denied' | 'error';

export function resolveMcpOAuthOutcome(param: string | null): McpOAuthOutcome | null {
  if (!param) return null;
  if (param === 'success' || param === 'denied') return param;
  return 'error';
}

/**
 * Outcome → toast routing. A denial is a user decision, so it gets an
 * informational toast, not an error. Kept as data (not branches) so the
 * settings page effect stays flat.
 */
export const MCP_OAUTH_TOAST: Record<
  McpOAuthOutcome,
  { kind: 'success' | 'info' | 'error'; key: string }
> = {
  success: { kind: 'success', key: 'settings.mcp.oauth_success' },
  denied: { kind: 'info', key: 'settings.mcp.oauth_denied' },
  error: { kind: 'error', key: 'settings.mcp.oauth_error' },
};
