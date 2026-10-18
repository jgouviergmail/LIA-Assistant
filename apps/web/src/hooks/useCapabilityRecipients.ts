'use client';

import { z } from '@/lib/zod';
import { useApplicationAccountQuery } from './useApplicationAccountQuery';

const recipientsSchema = z.array(
  z
    .object({
      id: z.string().uuid(),
      status: z.enum(['pending', 'accepted']),
      peer_display_name: z.string(),
    })
    .passthrough()
);

/** A closed dialog costs nothing; old-account recipient lists are never reused. */
export function useCapabilityRecipients() {
  const query = useApplicationAccountQuery<unknown>('/peers/connections', 'CapabilityRecipients');
  const parsed = query.data === undefined ? null : recipientsSchema.safeParse(query.data);
  return {
    recipients: parsed?.success ? parsed.data.filter(peer => peer.status === 'accepted') : [],
    loading: query.loading,
    error:
      query.error ?? (parsed && !parsed.success ? new Error('Invalid recipients response') : null),
  };
}
