'use client';
import { useCallback } from 'react';
import { useAuth } from '@/hooks/useAuth';
import { useApplicationAccountQuery } from '@/hooks/useApplicationAccountQuery';
import { useApplicationAccountState } from '@/hooks/useApplicationAccountState';
import { useApplicationResourceSync } from '@/hooks/useApplicationResourceSync';
import type { SmsSettings, SmsTokenPage, SmsBlockPage } from '@/types/sms';

type Cursor = { after_id: string; as_of: string } | undefined;
/** Bounded metadata pages and source-owned resource invalidation. */
export function useSmsSettings(enabled = true) {
  const { user } = useAuth();
  const [tokenCursor, setTokenCursor] = useApplicationAccountState<Cursor>(user?.id, undefined);
  const [blockCursor, setBlockCursor] = useApplicationAccountState<Cursor>(user?.id, undefined);
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
  const blocks = useApplicationAccountQuery<SmsBlockPage>(
    '/sms/blocked-senders',
    'useSmsSettings',
    enabled,
    undefined,
    { params: { limit: 20, ...blockCursor } }
  );
  const { refetch: refreshSettings } = settings;
  const { refetch: refreshTokens } = tokens;
  const { refetch: refreshBlocks } = blocks;
  const refresh = useCallback(async () => {
    setTokenCursor(undefined);
    setBlockCursor(undefined);
    await Promise.all([
      refreshSettings(),
      ...(!tokenCursor ? [refreshTokens()] : []),
      ...(!blockCursor ? [refreshBlocks()] : []),
    ]);
  }, [
    refreshSettings,
    refreshTokens,
    refreshBlocks,
    tokenCursor,
    blockCursor,
    setTokenCursor,
    setBlockCursor,
  ]);
  useApplicationResourceSync(enabled ? user?.id : undefined, 'sms', refresh);
  return {
    settings,
    tokens,
    blocks,
    refresh,
    tokenCursor,
    blockCursor,
    setTokenCursor,
    setBlockCursor,
  };
}
