import { z } from '@/lib/zod';
import { isSafeRedirectUrl } from '@/lib/safe-navigation';
import { applicationCommandStatusSchema, type ApplicationCommandStatus } from '@/types/application-commands';

const selection = z.object({ id: z.string().uuid(), requires_provider_authorization: z.literal(true),
  requires_original_browser_completion: z.literal(true) });
const startResponse = z.object({ command_id: z.string().uuid(), authorization_url: z.string().max(16_384) }).strict();
const savedReceipt = z.object({ server_id: z.string().uuid(), authorization_saved: z.literal(true), connection_verified: z.literal(false) });
const pendingError = z.object({ status: z.literal(409), data: z.object({ detail: z.object({ error_code: z.literal('OAUTH_PENDING') }) }) });

export function personalMCPOAuthSelection(status: ApplicationCommandStatus) {
  const observed = status.phase === 'resuming' ? status.prior_outcome : status.outcome;
  const result = selection.safeParse(observed?.values.personal_mcp_oauth);
  return result.success ? result.data : null;
}

export function personalMCPOAuthURL(value: unknown, commandId: string): string | null {
  const result = startResponse.safeParse(value);
  if (!result.success || result.data.command_id !== commandId || !isSafeRedirectUrl(result.data.authorization_url)) return null;
  return result.data.authorization_url;
}

export function acceptsPersonalMCPOAuth(value: unknown, status: ApplicationCommandStatus): boolean {
  const result = applicationCommandStatusSchema.safeParse(value);
  if (!result.success || result.data.command_id !== status.command_id || result.data.operation_id !== 'personal_mcp.oauth_authorize' ||
      result.data.phase !== 'committed' || !result.data.outcome?.committed) return false;
  const receipt = savedReceipt.safeParse(result.data.outcome.values.personal_mcp_oauth);
  return receipt.success && receipt.data.server_id === personalMCPOAuthSelection(status)?.id;
}

export function isPersonalMCPOAuthPending(error: unknown): boolean { return pendingError.safeParse(error).success; }

export function personalMCPOAuthMessage(status: ApplicationCommandStatus, mode: string, expired: boolean): string {
  if (mode === 'done' || status.outcome?.committed) return 'mcp_oauth_saved';
  if (mode === 'uncertain' || status.outcome?.error_code === 'COMPLETION_UNKNOWN') return 'secure_unknown';
  if (expired || status.phase === 'expired') return 'secure_expired';
  if (status.phase === 'failed' || status.phase === 'conflict') return 'secure_failed';
  if (mode === 'busy') return 'secure_running';
  if (mode === 'pending') return 'mcp_oauth_pending';
  return status.phase === 'resuming' ? 'mcp_oauth_returned' : 'mcp_oauth_waiting';
}
