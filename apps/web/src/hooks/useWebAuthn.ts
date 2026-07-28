/**
 * Passkey (WebAuthn) hooks — security program D1.
 *
 * `useWebAuthn` drives the two browser ceremonies (enrollment, login);
 * `usePasskeys` manages the Security-settings credential list;
 * `useAuthFeatures` exposes the instance's strong-auth availability so the
 * UI can hide passkey affordances when MFA is disabled server-side.
 */

'use client';

import { useCallback } from 'react';
import apiClient from '@/lib/api-client';
import { useApiQuery } from '@/hooks/useApiQuery';
import {
  parseCreationOptions,
  parseRequestOptions,
  serializeAuthenticationCredential,
  serializeRegistrationCredential,
} from '@/lib/webauthn';

export interface AuthFeatures {
  mfa_enabled: boolean;
}

export interface PasskeyCredential {
  id: string;
  label: string | null;
  device_type: string | null;
  backed_up: boolean;
  transports: string[] | null;
  created_at: string;
  last_used_at: string | null;
}

interface WebAuthnOptionsResponse {
  options: string;
}

interface WebAuthnAuthOptionsResponse {
  challenge_id: string;
  options: string;
}

interface AuthUserResponse {
  user: { id: string; email: string };
  message: string;
}

/** Instance-level strong-auth availability (public endpoint, always mounted). */
export function useAuthFeatures(): { features: AuthFeatures | undefined; loading: boolean } {
  const { data, loading } = useApiQuery<AuthFeatures>('/auth/features', {
    componentName: 'useAuthFeatures',
  });
  return { features: data, loading };
}

/** Browser-ceremony drivers (enrollment + login). */
export function useWebAuthn() {
  const registerPasskey = useCallback(async (label?: string): Promise<PasskeyCredential> => {
    const { options } = await apiClient.post<WebAuthnOptionsResponse>(
      '/auth/webauthn/register/options'
    );
    const credential = (await navigator.credentials.create(
      parseCreationOptions(options)
    )) as PublicKeyCredential | null;
    if (!credential) {
      throw new Error('Passkey ceremony cancelled');
    }
    return apiClient.post<PasskeyCredential>('/auth/webauthn/register/verify', {
      credential: serializeRegistrationCredential(credential),
      label: label || null,
    });
  }, []);

  const authenticateWithPasskey = useCallback(
    async (opts?: { conditional?: boolean; signal?: AbortSignal }): Promise<AuthUserResponse> => {
      const { challenge_id, options } = await apiClient.post<WebAuthnAuthOptionsResponse>(
        '/auth/webauthn/authenticate/options'
      );
      const request = parseRequestOptions(options);
      const credential = (await navigator.credentials.get({
        ...request,
        ...(opts?.conditional
          ? { mediation: 'conditional' as CredentialMediationRequirement }
          : {}),
        ...(opts?.signal ? { signal: opts.signal } : {}),
      })) as PublicKeyCredential | null;
      if (!credential) {
        throw new Error('Passkey ceremony cancelled');
      }
      return apiClient.post<AuthUserResponse>('/auth/webauthn/authenticate/verify', {
        challenge_id,
        credential: serializeAuthenticationCredential(credential),
      });
    },
    []
  );

  return { registerPasskey, authenticateWithPasskey };
}

/** Credential list management for the Security settings section. */
export function usePasskeys(enabled: boolean = true) {
  const { data, loading, error, refetch } = useApiQuery<PasskeyCredential[]>(
    '/auth/webauthn/credentials',
    {
      componentName: 'usePasskeys',
      initialData: [],
      enabled,
    }
  );

  const renamePasskey = useCallback(
    async (id: string, label: string | null): Promise<void> => {
      await apiClient.patch(`/auth/webauthn/credentials/${id}`, { label });
      await refetch();
    },
    [refetch]
  );

  const deletePasskey = useCallback(
    async (id: string): Promise<void> => {
      await apiClient.delete(`/auth/webauthn/credentials/${id}`);
      await refetch();
    },
    [refetch]
  );

  return { passkeys: data ?? [], loading, error, refetch, renamePasskey, deletePasskey };
}
