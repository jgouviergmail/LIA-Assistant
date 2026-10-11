import { z } from '@/lib/zod';

/** Public original-browser scope; private SQL/file proof is never accepted here. */
export const documentUploadSelectionSchema = z.object({
  space: z.object({ id: z.string().uuid(), name: z.string(), description: z.string().nullable(),
    is_active: z.boolean(), kind: z.string().nullable() }).strict(),
  document_count: z.number().int().nonnegative(), max_documents: z.number().int().positive(),
  max_file_size_bytes: z.number().int().positive(), allowed_content_types: z.array(z.string()).min(1),
  browser_file_confirmation_required: z.literal(true), indexing_requested: z.literal(true),
  indexing_cost_may_apply: z.literal(true),
}).strict();

export type DocumentUploadSelection = z.infer<typeof documentUploadSelectionSchema>;

export const documentUploadResultSchema = z.object({
  success: z.literal(true), phase: z.literal('committed'), committed: z.literal(true),
  no_op: z.literal(false), error_code: z.null(), interaction: z.null(),
  values: z.object({ document_id: z.string().uuid(), space_id: z.string().uuid(),
    upload_accepted: z.literal(true), status: z.literal('pending'), indexing_completed: z.literal(false) }).strict(),
}).strict();
