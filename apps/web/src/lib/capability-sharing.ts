import { z } from '@/lib/zod';

export const capabilityOriginSchema = z
  .object({
    sender_display_name: z.string().nullable(),
    shared_at: z.string().datetime({ offset: true }),
    transfer_id: z.string().uuid(),
  })
  .strict();
export type CapabilityOrigin = z.infer<typeof capabilityOriginSchema>;

export const capabilityKindSchema = z.enum(['skill', 'mcp', 'plugin']);
export type CapabilityKind = z.infer<typeof capabilityKindSchema>;

export interface CapabilitySelection {
  kind: CapabilityKind;
  id: string;
  name: string;
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
