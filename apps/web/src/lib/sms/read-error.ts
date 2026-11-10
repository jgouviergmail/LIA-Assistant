/** Shared, structural handling of bounded search and stale archive continuations. */
import { z } from '@/lib/zod';
import { ApiError } from '@/lib/api-client';

const refusal = z.object({ detail: z.object({ error_code: z.string() }) });
export function smsReadErrorKey(error: Error | null): string {
  if (!(error instanceof ApiError) || error.status !== 409) return 'sms.unavailable';
  const data = refusal.safeParse(error.data);
  if (!data.success) return 'sms.unavailable';
  if (data.data.detail.error_code === 'QUERY_TOO_BROAD') return 'sms.too_broad';
  if (data.data.detail.error_code === 'STALE_CURSOR') return 'sms.stale_cursor';
  return 'sms.unavailable';
}
