import { z } from '@/lib/zod';
import type { ApplicationCommandStatus } from '@/types/application-commands';
import { applicationCommandStatusSchema } from '@/types/application-commands';

export const personalMCPConfigurationSelectionSchema = z
  .object({
    server_id: z.string().uuid().nullable(),
    creating: z.boolean(),
    requires_private_browser_form: z.literal(true),
    // A key of the known catalogue the assistant proposed to add: the form
    // opens filled with that server's PUBLIC facts. Present only when chosen.
    known_server: z.string().min(1).optional(),
  })
  .strict()
  .refine(value => value.creating === (value.server_id === null))
  .refine(value => value.creating || value.known_server === undefined);

/** Browser-only original DTO projection. Cached schemas and stored diagnostic text are discarded. */
export const personalMCPFormSourceSchema = z.object({
  id: z.string().uuid(),
  name: z.string().min(1).max(100),
  url: z.string().min(1).max(2048),
  auth_type: z.enum(['none', 'api_key', 'bearer', 'oauth2']),
  header_name: z.string().nullable(),
  oauth_scopes: z.string().nullable(),
  domain_description: z.string().nullable(),
  timeout_seconds: z.number().int().min(5).max(120),
  iterative_mode: z.boolean(),
  has_credentials: z.boolean(),
  has_oauth_credentials: z.boolean(),
});
export const personalMCPFormListSchema = z.object({
  servers: z.array(personalMCPFormSourceSchema),
  total: z.number().int().nonnegative(),
});

export function personalMCPConfigurationSelection(status: ApplicationCommandStatus) {
  const selected = personalMCPConfigurationSelectionSchema.safeParse(
    status.outcome?.values.personal_mcp_configuration
  );
  return selected.success ? selected.data : null;
}

export function acceptsPersonalMCPConfiguration(
  value: unknown,
  status: ApplicationCommandStatus
): boolean {
  const result = applicationCommandStatusSchema.safeParse(value);
  if (
    !result.success ||
    result.data.command_id !== status.command_id ||
    result.data.operation_id !== 'personal_mcp.configuration' ||
    result.data.phase !== 'committed' ||
    !result.data.outcome?.committed
  )
    return false;
  const receipt = z
    .object({
      server_id: z.string().uuid(),
      configuration_saved: z.literal(true),
      connection_verified: z.literal(false),
    })
    .safeParse(result.data.outcome.values.personal_mcp_configuration);
  const selected = personalMCPConfigurationSelection(status);
  return (
    receipt.success &&
    !!selected &&
    (selected.creating || receipt.data.server_id === selected.server_id)
  );
}

/**
 * The status line of the card.
 *
 * @param closed - The confirmation still waits for its form, and the instance
 *   has closed the personal servers since: the form cannot be offered, so the
 *   confirmed action cannot complete there. Everything the command itself
 *   says — saved, running, expired, failed, unknown — is said first.
 */
export function personalMCPConfigurationMessage(
  status: ApplicationCommandStatus,
  mode: string,
  expired: boolean,
  closed: boolean
): string {
  const message = commandMessage(status, mode, expired);
  return closed && message === 'mcp_configuration_waiting' ? 'secure_failed' : message;
}

/** What the command says of itself, whatever the instance offers now. */
function commandMessage(status: ApplicationCommandStatus, mode: string, expired: boolean): string {
  if (mode === 'done' || status.outcome?.committed) return 'mcp_configuration_saved';
  if (mode === 'uncertain' || status.outcome?.error_code === 'COMPLETION_UNKNOWN')
    return 'secure_unknown';
  if (expired || status.phase === 'expired') return 'secure_expired';
  if (status.phase === 'failed' || status.phase === 'conflict') return 'secure_failed';
  if (mode === 'busy' || status.phase === 'claimed' || status.phase === 'resuming')
    return 'secure_running';
  return 'mcp_configuration_waiting';
}
