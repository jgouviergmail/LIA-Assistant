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

import { useCallback, useRef } from 'react';
import { useTranslation } from 'react-i18next';

import { apiClient, ApiError } from '@/lib/api-client';
import { logger } from '@/lib/logger';
import { useApplicationAccountQuery } from '@/hooks/useApplicationAccountQuery';
import { useApplicationAccountLifetime } from '@/hooks/useApplicationAccountLifetime';
import { useApplicationAccountState } from '@/hooks/useApplicationAccountState';
import { useApplicationResourceSync } from '@/hooks/useApplicationResourceSync';
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
  const { t } = useTranslation();
  const {
    data,
    loading,
    error,
    refetch: read,
    setData,
    ownerId,
  } = useApplicationAccountQuery<TelephonyIdentity>(ENDPOINT, 'useTelephonyIdentity', enabled);
  const { lifetime, isCurrent } = useApplicationAccountLifetime(ownerId);
  const [isBusy, setIsBusy] = useApplicationAccountState(ownerId, false);
  const [codeExpiresInSeconds, setCodeExpiresInSeconds] = useApplicationAccountState<number | null>(
    ownerId,
    null
  );
  const queues = useRef(new Map<typeof lifetime, Promise<string | null>>());
  const refetch = useCallback(async () => {
    if (!isCurrent()) return;
    const previous = queues.current.get(lifetime) ?? Promise.resolve(null);
    const reading = previous.then(async () => {
      if (isCurrent()) await read();
      return null;
    });
    // Reads and writes share one queue, so an older read cannot undo a save.
    queues.current.set(lifetime, reading);
    try {
      await reading;
    } finally {
      if (queues.current.get(lifetime) === reading) {
        queues.current.delete(lifetime);
        if (isCurrent()) setIsBusy(false);
      }
    }
  }, [lifetime, isCurrent, read, setIsBusy]);
  const release = useCallback(() => {}, []);
  useApplicationResourceSync(ownerId, 'phone_identity', refetch, release);

  /** Run one action; on success adopt the identity it returns (or re-read). */
  const run = useCallback(
    async (action: () => Promise<TelephonyIdentity | undefined | void>): Promise<string | null> => {
      if (!enabled || !ownerId || !isCurrent())
        return t('settings.telephony.identity.context_changed');
      setIsBusy(true);
      const previous = (queues.current.get(lifetime) ?? Promise.resolve(null)).catch(() => null);
      const writing = previous.then(async (): Promise<string | null> => {
        if (!isCurrent()) return t('settings.telephony.identity.context_changed');
        try {
          const next = await action();
          if (!isCurrent()) return t('settings.telephony.identity.context_changed');
          if (next) setData(next);
          else await read();
          return null;
        } catch (failure) {
          if (!isCurrent()) return t('settings.telephony.identity.context_changed');
          const status = failure instanceof ApiError ? failure.status : undefined;
          logger.warn('Telephony identity action refused', {
            component: 'useTelephonyIdentity',
            status,
          });
          // Preserve the original refusal if its recovery read also fails.
          if (status === 409) await read().catch(() => {});
          return refusalOf(failure);
        }
      });
      queues.current.set(lifetime, writing);
      try {
        return await writing;
      } finally {
        if (queues.current.get(lifetime) === writing) {
          queues.current.delete(lifetime);
          if (isCurrent()) setIsBusy(false);
        }
      }
    },
    [enabled, ownerId, isCurrent, lifetime, read, setData, setIsBusy, t]
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
        if (isCurrent()) setCodeExpiresInSeconds(started.expires_in_seconds);
      }),
    [run, isCurrent, setCodeExpiresInSeconds]
  );

  const confirmCode = useCallback(
    (code: string) =>
      run(async () => {
        const next = await apiClient.post<TelephonyIdentity>(`${ENDPOINT}/confirm`, { code });
        if (isCurrent()) setCodeExpiresInSeconds(null);
        return next;
      }),
    [run, isCurrent, setCodeExpiresInSeconds]
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
    identity: data ?? null,
    isLoading: loading && !data,
    isUnavailable: error instanceof ApiError && error.status === 404,
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
