/**
 * Resolution of the `mcp_oauth` callback marker appended by the backend
 * OAuth callback redirect (user MCP servers).
 *
 * The outcomes on the wire: `success`, `denied` (the user refused consent on
 * the authorization server — not a system error), `changed` (the server was
 * edited while the person consented, so the tokens were not stored), `error`,
 * and `pending` for a consent the assistant staged. Any unknown value degrades
 * to `error` because the URL is user-editable.
 */

import { z } from '@/lib/zod';

export type McpOAuthOutcome = 'success' | 'denied' | 'changed' | 'error' | 'pending';

/** Native MCP callbacks land in settings; a staged application command returns to its chat. */
export function resumeApplicationMCPOAuthReturn(
  outcome: McpOAuthOutcome,
  commandId: string | null
): void {
  if (outcome === 'pending' && z.string().uuid().safeParse(commandId).success)
    window.location.replace('/dashboard/chat');
}

export function resolveMcpOAuthOutcome(param: string | null): McpOAuthOutcome | null {
  if (!param) return null;
  if (param === 'success' || param === 'denied' || param === 'changed' || param === 'pending')
    return param;
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
  pending: { kind: 'info', key: 'settings.mcp.oauth_pending' },
  success: { kind: 'success', key: 'settings.mcp.oauth_success' },
  denied: { kind: 'info', key: 'settings.mcp.oauth_denied' },
  changed: { kind: 'error', key: 'settings.mcp.oauth_changed' },
  error: { kind: 'error', key: 'settings.mcp.oauth_error' },
};
