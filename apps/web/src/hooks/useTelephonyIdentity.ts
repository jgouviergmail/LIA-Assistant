'use client';

/**
 * The person's own phone number — declared, verified by a call (phone as a
 * channel, lots 1-2-5).
 *
 * LIA may call the account holder WITHOUT a confirmation card only on a number
 * they declared here and then heard LIA read a code on. This hook is the whole
 * client of that contract: one read on mount, every action re-reading the
 * identity the server returns, and a refusal handed back as the backend's own
 * translated sentence — the field shows it, nothing is guessed client-side.
 *
 * A 404 means the telephony feature is off; the hook then stays silent for
 * good, like the calls list does.
 */

import { useCallback, useEffect, useState } from 'react';

import { apiClient, ApiError } from '@/lib/api-client';
import { logger } from '@/lib/logger';
import { useStaleGuard } from '@/hooks/useStaleGuard';
import type {
  PhoneCallMode,
  TelephonyIdentity,
  TelephonyIdentityVerifyStart,
} from '@/types/telephony';

export interface UseTelephonyIdentityReturn {
  identity: TelephonyIdentity | null;
  /** True only on the very first load. */
  isLoading: boolean;
  /** The feature is off (router absent → 404) — callers render nothing. */
  isUnavailable: boolean;
  /** True while an action is in flight. */
  isBusy: boolean;
  /** How long the spoken code stays valid, once a verification call left. */
  codeExpiresInSeconds: number | null;
  /** Each action resolves to `null` on success, or the backend's sentence. */
  setNumber: (raw: string) => Promise<string | null>;
  clearNumber: () => Promise<string | null>;
  startVerification: () => Promise<string | null>;
  confirmCode: (code: string) => Promise<string | null>;
  setRichContext: (enabled: boolean) => Promise<string | null>;
  /** Replace the set of domains switched off for the person's own calls (lot 8). */
  setDisabledDomains: (domains: string[]) => Promise<string | null>;
  /** Choose how the person's own calls run: Live or Live direct (ADR-301). */
  setCallMode: (mode: PhoneCallMode) => Promise<string | null>;
  refetch: () => Promise<void>;
}

const ENDPOINT = '/telephony/identity';

/** The sentence to show for a refused action: the backend's, translated. */
function refusalOf(error: unknown): string {
  if (error instanceof ApiError) return error.message;
  return error instanceof Error ? error.message : String(error);
}

export function useTelephonyIdentity(enabled = true): UseTelephonyIdentityReturn {
  const [identity, setIdentity] = useState<TelephonyIdentity | null>(null);
  const [isLoading, setIsLoading] = useState(enabled);
  const [isUnavailable, setIsUnavailable] = useState(false);
  const [isBusy, setIsBusy] = useState(false);
  const [codeExpiresInSeconds, setCodeExpiresInSeconds] = useState<number | null>(null);
  const guard = useStaleGuard();

  const refetch = useCallback(async () => {
    const isStale = guard.begin();
    try {
      const response = await apiClient.get<TelephonyIdentity>(ENDPOINT);
      if (isStale()) return;
      setIdentity(response);
    } catch (error) {
      if (isStale()) return;
      if (error instanceof ApiError && error.status === 404) {
        setIsUnavailable(true);
        setIdentity(null);
        return;
      }
      if (error instanceof TypeError) return;
      logger.error('Failed to fetch telephony identity', error as Error, {
        component: 'useTelephonyIdentity',
      });
    } finally {
      if (!isStale()) setIsLoading(false);
    }
  }, [guard]);

  useEffect(() => {
    if (!enabled || isUnavailable) {
      setIsLoading(false);
      return;
    }
    void refetch();
  }, [enabled, isUnavailable, refetch]);

  /** Run one action; on success adopt the identity it returns (or re-read). */
  const run = useCallback(
    async (action: () => Promise<TelephonyIdentity | undefined | void>): Promise<string | null> => {
      setIsBusy(true);
      try {
        const next = await action();
        if (next) setIdentity(next);
        else await refetch();
        return null;
      } catch (error) {
        const status = error instanceof ApiError ? error.status : undefined;
        logger.warn('Telephony identity action refused', {
          component: 'useTelephonyIdentity',
          status,
        });
        // A conflict means the page and the server disagree on the state (a
        // code that expired, a number that changed): re-read, so the form
        // stops asking for something the server no longer expects.
        if (status === 409) await refetch();
        return refusalOf(error);
      } finally {
        setIsBusy(false);
      }
    },
    [refetch]
  );

  const setNumber = useCallback(
    (raw: string) =>
      run(() => apiClient.put<TelephonyIdentity>(`${ENDPOINT}/number`, { phone_number: raw })),
    [run]
  );

  const clearNumber = useCallback(
    () =>
      run(async () => {
        await apiClient.delete(`${ENDPOINT}/number`);
      }),
    [run]
  );

  const startVerification = useCallback(
    () =>
      run(async () => {
        const started = await apiClient.post<TelephonyIdentityVerifyStart>(`${ENDPOINT}/verify`);
        setCodeExpiresInSeconds(started.expires_in_seconds);
      }),
    [run]
  );

  const confirmCode = useCallback(
    (code: string) =>
      run(async () => {
        const next = await apiClient.post<TelephonyIdentity>(`${ENDPOINT}/confirm`, { code });
        setCodeExpiresInSeconds(null);
        return next;
      }),
    [run]
  );

  const setRichContext = useCallback(
    (value: boolean) =>
      run(() => apiClient.patch<TelephonyIdentity>(ENDPOINT, { rich_context_enabled: value })),
    [run]
  );

  const setDisabledDomains = useCallback(
    (domains: string[]) =>
      run(() => apiClient.patch<TelephonyIdentity>(ENDPOINT, { disabled_domains: domains })),
    [run]
  );

  const setCallMode = useCallback(
    (mode: PhoneCallMode) =>
      run(() => apiClient.patch<TelephonyIdentity>(ENDPOINT, { call_mode: mode })),
    [run]
  );

  return {
    identity,
    isLoading,
    isUnavailable,
    isBusy,
    codeExpiresInSeconds,
    setNumber,
    clearNumber,
    startVerification,
    confirmCode,
    setRichContext,
    setDisabledDomains,
    setCallMode,
    refetch,
  };
}
