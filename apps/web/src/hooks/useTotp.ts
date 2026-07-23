/**
 * TOTP second-factor management hook (security program D1, Lot 2).
 *
 * Drives the enrollment lifecycle against the backend: status, enroll
 * (secret + QR revealed once), confirm (activates + returns backup codes
 * once), disable, and backup-code regeneration.
 */

'use client';

import { useCallback } from 'react';
import apiClient from '@/lib/api-client';
import { useApiQuery } from '@/hooks/useApiQuery';

export interface TotpStatus {
  active: boolean;
  confirmed_at: string | null;
  backup_codes_remaining: number;
}

export interface TotpEnrollment {
  secret: string;
  otpauth_uri: string;
  qr_data_uri: string;
}

interface BackupCodesResponse {
  backup_codes: string[];
  message: string;
}

export function useTotp(enabled: boolean = true) {
  const {
    data: status,
    loading,
    refetch,
  } = useApiQuery<TotpStatus>('/auth/totp/status', {
    componentName: 'useTotp',
    enabled,
  });

  const enroll = useCallback(async (): Promise<TotpEnrollment> => {
    return apiClient.post<TotpEnrollment>('/auth/totp/enroll');
  }, []);

  const confirm = useCallback(
    async (code: string): Promise<string[]> => {
      const response = await apiClient.post<BackupCodesResponse>('/auth/totp/confirm', { code });
      await refetch();
      return response.backup_codes;
    },
    [refetch]
  );

  const disable = useCallback(async (): Promise<void> => {
    await apiClient.delete('/auth/totp');
    await refetch();
  }, [refetch]);

  const regenerateBackupCodes = useCallback(async (): Promise<string[]> => {
    const response = await apiClient.post<BackupCodesResponse>(
      '/auth/totp/backup-codes/regenerate'
    );
    await refetch();
    return response.backup_codes;
  }, [refetch]);

  return { status, loading, refetch, enroll, confirm, disable, regenerateBackupCodes };
}
