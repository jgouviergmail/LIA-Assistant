'use client';
import { useCallback } from 'react';
import { useAuth } from '@/hooks/useAuth';
import { useApplicationAccountQuery } from '@/hooks/useApplicationAccountQuery';
import { useApplicationAccountState } from '@/hooks/useApplicationAccountState';
import { useApplicationResourceSync } from '@/hooks/useApplicationResourceSync';
import type { SmsSettings, SmsTokenPage } from '@/types/sms';

type Cursor = { after_id: string; as_of: string } | undefined;
/**
 * The SMS settings' bounded metadata pages and source-owned resource
 * invalidation. The blocked senders are the « SMS » page's
 * (`useSmsBlockedSenders`), with the archive and its erasure.
 */
export function useSmsSettings(enabled = true) {
  const { user } = useAuth();
  const [tokenCursor, setTokenCursor] = useApplicationAccountState<Cursor>(user?.id, undefined);
  const settings = useApplicationAccountQuery<SmsSettings>(
    '/sms/settings',
    'useSmsSettings',
    enabled
  );
  const tokens = useApplicationAccountQuery<SmsTokenPage>(
    '/sms/tokens',
    'useSmsSettings',
    enabled,
    undefined,
    { params: { limit: 20, ...tokenCursor } }
  );
  const { refetch: refreshSettings } = settings;
  const { refetch: refreshTokens } = tokens;
  const refresh = useCallback(async () => {
    setTokenCursor(undefined);
    await Promise.all([refreshSettings(), ...(!tokenCursor ? [refreshTokens()] : [])]);
  }, [refreshSettings, refreshTokens, tokenCursor, setTokenCursor]);
  useApplicationResourceSync(enabled ? user?.id : undefined, 'sms', refresh);
  return {
    settings,
    tokens,
    refresh,
    tokenCursor,
    setTokenCursor,
  };
}
