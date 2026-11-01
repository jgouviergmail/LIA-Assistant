'use client';
import { useCallback } from 'react';
import { useAuth } from '@/hooks/useAuth';
import { useApplicationAccountQuery } from '@/hooks/useApplicationAccountQuery';
import { useApplicationAccountState } from '@/hooks/useApplicationAccountState';
import { useApplicationResourceSync } from '@/hooks/useApplicationResourceSync';
import type { SmsBlockPage } from '@/types/sms';

type Cursor = { after_id: string; as_of: string } | undefined;

/**
 * The account's blocked senders, one bounded page at a time, for the « SMS »
 * page that manages them. An SMS command landing anywhere re-reads them from
 * their first page (the source-owned `sms` resource).
 */
export function useSmsBlockedSenders(enabled = true) {
  const { user } = useAuth();
  const [cursor, setCursor] = useApplicationAccountState<Cursor>(user?.id, undefined);
  const blocks = useApplicationAccountQuery<SmsBlockPage>(
    '/sms/blocked-senders',
    'useSmsBlockedSenders',
    enabled,
    undefined,
    { params: { limit: 20, ...cursor } }
  );
  const { refetch } = blocks;
  const refresh = useCallback(async () => {
    // Back to the first page: a cursor change re-reads by itself.
    setCursor(undefined);
    if (!cursor) await refetch();
  }, [cursor, refetch, setCursor]);
  useApplicationResourceSync(enabled ? user?.id : undefined, 'sms', refresh);
  return { blocks, cursor, setCursor, refresh };
}
