'use client';

import { useCallback } from 'react';
import type { CapabilitySelection } from '@/lib/capability-sharing';
import { useApplicationAccountState } from './useApplicationAccountState';
import { useAppConfig } from './useAppConfig';

export function useCapabilitySharing(ownerId: string | undefined) {
  const { config } = useAppConfig();
  const [selection, share] = useApplicationAccountState<CapabilitySelection | null>(ownerId, null);
  const close = useCallback(() => share(null), [share]);
  return { selection, share, close, enabled: config?.features?.peers_enabled === true };
}
