import { z } from '@/lib/zod';

const stamp = {
  version: z.literal('email-event-v1-phishing'),
  evidence_scope: z.enum(['metadata', 'snippet', 'body', 'summary', 'partial_body', 'event']),
  evaluated_at: z.string().datetime({ offset: true }),
  valid_until: z.string().datetime({ offset: true }),
};
const classification = z.discriminatedUnion('kind', [
  z
    .object({
      ...stamp,
      kind: z.literal('email'),
      category: z.enum(['unknown', 'professional', 'personal', 'spam', 'phishing_scam']),
      priority: z.enum(['unknown', 'normal', 'urgent', 'critical']),
    })
    .strict(),
  z
    .object({
      ...stamp,
      kind: z.literal('event'),
      category: z.enum(['unknown', 'professional', 'personal']),
    })
    .strict(),
]);
export type ContentClassification = z.infer<typeof classification>;
export function readClassification(value: unknown): ContentClassification | null {
  const parsed = classification.safeParse(value);
  if (
    !parsed.success ||
    Date.parse(parsed.data.valid_until) <= Date.parse(parsed.data.evaluated_at)
  )
    return null;
  return parsed.data;
}
