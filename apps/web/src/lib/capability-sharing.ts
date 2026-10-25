import { z } from '@/lib/zod';

export const capabilityOriginSchema = z
  .object({
    sender_display_name: z.string().nullable(),
    shared_at: z.string().datetime({ offset: true }),
    transfer_id: z.string().uuid(),
  })
  .strict();
export type CapabilityOrigin = z.infer<typeof capabilityOriginSchema>;

/** One recipient the owner's capability was shared with — its latest share (sender side). */
export const capabilityShareSchema = z
  .object({
    recipient_id: z.string().uuid(),
    recipient_display_name: z.string().nullable(),
    shared_at: z.string().datetime({ offset: true }),
    transfer_id: z.string().uuid(),
    complete: z.boolean(),
    can_share_again: z.boolean(),
  })
  .strict();
export type CapabilityShare = z.infer<typeof capabilityShareSchema>;

export const capabilityKindSchema = z.enum(['skill', 'mcp', 'plugin']);
export type CapabilityKind = z.infer<typeof capabilityKindSchema>;

export interface CapabilitySelection {
  kind: CapabilityKind;
  id: string;
  name: string;
  /** Accounts the server's sharing policy closes for this capability — never offered. */
  blockedRecipientIds?: readonly string[];
}

/** The recipients a capability may not be shared with again, as the server decided. */
export function blockedRecipients(shares: readonly CapabilityShare[] | null | undefined): string[] {
  return (shares ?? []).filter(share => !share.can_share_again).map(share => share.recipient_id);
}

export const capabilityTransferSchema = z
  .object({
    id: z.string().uuid(),
    kind: capabilityKindSchema,
    name: z.string(),
    status: z.enum(['preparing', 'installing', 'installed', 'partial', 'failed', 'cancelled']),
    digest: z.string().regex(/^[0-9a-f]{64}$/),
    files: z.array(z.object({ path: z.string(), size: z.number().int().nonnegative() }).strict()),
    omitted: z.array(z.string()),
    requires_credentials: z.boolean(),
    created_at: z.string().datetime({ offset: true }),
    transferred_at: z.string().datetime({ offset: true }).nullable(),
    components: z.array(
      z
        .object({
          kind: capabilityKindSchema,
          key: z.string(),
          resource_id: z.string().uuid().nullable(),
          installed: z.boolean(),
          error_code: z.string().nullable(),
        })
        .strict()
    ),
    error_code: z.string().nullable(),
  })
  .strict();
export type CapabilityTransfer = z.infer<typeof capabilityTransferSchema>;
