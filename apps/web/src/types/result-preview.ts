import { z } from '@/lib/zod';

/** Ephemeral side channel: bounded, reversible and never persisted with chat history. */
export const qualifiedCollectionSchema = z
  .object({
    kind: z.enum(['EMAIL', 'EVENT', 'TASK', 'FILE', 'REMINDER', 'TICKET', 'MCP_RESULT', 'NOTE']),
    items: z
      .array(
        z.object({
          id: z.string().min(1).max(512),
          title: z.string().max(180),
          excerpt: z.string().max(600),
          verdict: z.enum(['match', 'non_match', 'unknown']),
        })
      )
      .max(100),
    candidate_count: z.number().int().nonnegative(),
    evaluated_count: z.number().int().min(0).max(24),
    omitted_count: z.number().int().nonnegative(),
  })
  .refine(
    value =>
      value.candidate_count === value.items.length + value.omitted_count &&
      value.evaluated_count <= value.items.length &&
      new Set(value.items.map(item => item.id)).size === value.items.length
  );

export type QualifiedCollection = z.infer<typeof qualifiedCollectionSchema>;
