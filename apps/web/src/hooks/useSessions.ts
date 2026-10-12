/**
 * Device sessions hooks (security program D2, Lot 4).
 *
 * "My devices": list live sessions (bounded metadata), revoke one, revoke
 * all others (step-up guarded at the call site), and the new-login
 * notification preference (A4).
 */

'use client';

import { useCallback } from 'react';
import apiClient from '@/lib/api-client';
import { useApplicationAccountQuery } from '@/hooks/useApplicationAccountQuery';
import { useApplicationResourceSync } from '@/hooks/useApplicationResourceSync';

const releaseSessionState = () => {};

export interface DeviceSession {
  id: string;
  current: boolean;
  ua_family: string | null;
  os_family: string | null;
  ip_trunc: string | null;
  auth_methods: string[];
  created_at: string;
  last_seen_at: string | null;
  device_name: string | null;
}

export function useSessions() {
  const { ownerId, isCurrent, data, loading, error, refetch } = useApplicationAccountQuery<
    DeviceSession[]
  >('/auth/sessions', 'useSessions');
  useApplicationResourceSync(ownerId, 'device_sessions', refetch, releaseSessionState);

  const revokeSession = useCallback(
    async (id: string): Promise<void> => {
      if (!isCurrent()) throw new Error('Session operation is no longer current');
      await apiClient.delete(`/auth/sessions/${id}`);
      await refetch();
    },
    [refetch, isCurrent]
  );

  const revokeOthers = useCallback(async (): Promise<number> => {
    if (!isCurrent()) throw new Error('Session operation is no longer current');
    const response = await apiClient.post<{ revoked: number }>('/auth/sessions/revoke-others');
    await refetch();
    return response.revoked;
  }, [refetch, isCurrent]);

  return { sessions: data ?? [], loading, error, refetch, revokeSession, revokeOthers };
}

export function useLoginNotificationsPreference() {
  const setEnabled = useCallback(async (enabled: boolean): Promise<void> => {
    await apiClient.patch('/auth/me/login-notifications-preference', { enabled });
  }, []);
  return { setEnabled };
}
