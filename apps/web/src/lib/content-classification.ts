import { z } from '@/lib/zod';

const stamp = {
  // v2 adds whether an e-mail expects a reply (ADR-374); an archived v1 is still read.
  version: z.enum(['email-event-v1-phishing', 'email-event-v2-reply']),
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
      /** Undecided when absent or null; always false for spam and phishing. */
      reply_expected: z.boolean().nullable().optional(),
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
