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
import { useApiQuery } from '@/hooks/useApiQuery';

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
  const { data, loading, error, refetch } = useApiQuery<DeviceSession[]>('/auth/sessions', {
    componentName: 'useSessions',
    initialData: [],
  });

  const revokeSession = useCallback(
    async (id: string): Promise<void> => {
      await apiClient.delete(`/auth/sessions/${id}`);
      await refetch();
    },
    [refetch]
  );

  const revokeOthers = useCallback(async (): Promise<number> => {
    const response = await apiClient.post<{ revoked: number }>('/auth/sessions/revoke-others');
    await refetch();
    return response.revoked;
  }, [refetch]);

  return { sessions: data ?? [], loading, error, refetch, revokeSession, revokeOthers };
}

export function useLoginNotificationsPreference() {
  const setEnabled = useCallback(async (enabled: boolean): Promise<void> => {
    await apiClient.patch('/auth/me/login-notifications-preference', { enabled });
  }, []);
  return { setEnabled };
}
