/**
 * Hook for the per-user telephony (ElevenLabs) connector single-screen form.
 *
 * The whole configuration is exposed at once (BYO key, calling number, post-call
 * webhook secret); only the number list is intrinsically dependent — it can only
 * be fetched once the key is validated, so the number picker enables after
 * `validateKey`. Editing the key invalidates a previously loaded list (the
 * numbers belong to the old key's workspace).
 *
 * Calls are billed on the user's own ElevenLabs/telephony accounts (D-9).
 */

import { useCallback, useState } from 'react';
import { useTranslation } from 'react-i18next';

import apiClient from '@/lib/api-client';
import { logger } from '@/lib/logger';

export interface TelephonyPhoneNumber {
  phone_number_id: string;
  phone_number: string;
  provider?: string | null;
}

interface ValidateKeyResponse {
  is_valid: boolean;
  message: string;
  numbers: TelephonyPhoneNumber[];
}

interface ActivateResponse {
  status: string;
  agent_id: string;
  agent_phone_number_id: string;
}

interface UseTelephonyOptions {
  onSuccess?: () => void;
  onError?: (error: string) => void;
}

/** Public URL the user pastes into their ElevenLabs workspace webhook config. */
export function buildTelephonyWebhookUrl(): string {
  const apiBaseUrl = process.env.NEXT_PUBLIC_API_URL || '';
  return `${apiBaseUrl}/api/v1/telephony/webhook`;
}

export function useTelephony({ onSuccess, onError }: UseTelephonyOptions = {}) {
  const { t } = useTranslation();
  const [apiKey, setApiKeyRaw] = useState('');
  const [numbers, setNumbers] = useState<TelephonyPhoneNumber[]>([]);
  const [selectedNumberId, setSelectedNumberId] = useState<string | null>(null);
  const [webhookSecret, setWebhookSecret] = useState('');
  const [isValidating, setIsValidating] = useState(false);
  const [isActivating, setIsActivating] = useState(false);
  const [activated, setActivated] = useState(false);
  const [error, setError] = useState<string | null>(null);

  /** Editing the key invalidates the loaded numbers (they belong to the old key). */
  const setApiKey = useCallback(
    (value: string) => {
      setApiKeyRaw(value);
      if (numbers.length > 0) {
        setNumbers([]);
        setSelectedNumberId(null);
      }
    },
    [numbers.length]
  );

  const validateKey = useCallback(async () => {
    setIsValidating(true);
    setError(null);
    try {
      const data = await apiClient.post<ValidateKeyResponse>('/telephony/connector/validate-key', {
        api_key: apiKey,
      });
      if (!data.is_valid) {
        setError(t('settings.connectors.telephony.invalid_key'));
        return;
      }
      const loaded = data.numbers || [];
      setNumbers(loaded);
      if (loaded.length === 0) {
        setError(t('settings.connectors.telephony.no_numbers'));
        return;
      }
      // Single number: preselect it — nothing left to choose.
      if (loaded.length === 1) {
        setSelectedNumberId(loaded[0].phone_number_id);
      }
    } catch (err) {
      const msg = err instanceof Error ? err.message : 'Validation failed';
      logger.error('Telephony key validation failed', err as Error, {
        component: 'useTelephony',
      });
      setError(msg);
      onError?.(msg);
    } finally {
      setIsValidating(false);
    }
  }, [apiKey, t, onError]);

  const activate = useCallback(async () => {
    if (!selectedNumberId) return;
    setIsActivating(true);
    setError(null);
    try {
      const selected = numbers.find(n => n.phone_number_id === selectedNumberId);
      await apiClient.post<ActivateResponse>('/telephony/connector/activate', {
        api_key: apiKey,
        agent_phone_number_id: selectedNumberId,
        webhook_secret: webhookSecret,
        caller_number_display: selected?.phone_number ?? null,
      });
      setActivated(true);
      onSuccess?.();
    } catch (err) {
      const msg = err instanceof Error ? err.message : 'Activation failed';
      logger.error('Telephony activation failed', err as Error, { component: 'useTelephony' });
      setError(msg);
      onError?.(msg);
    } finally {
      setIsActivating(false);
    }
  }, [apiKey, selectedNumberId, webhookSecret, numbers, onSuccess, onError]);

  const reset = useCallback(() => {
    setApiKeyRaw('');
    setNumbers([]);
    setSelectedNumberId(null);
    setWebhookSecret('');
    setError(null);
    setIsValidating(false);
    setIsActivating(false);
    setActivated(false);
  }, []);

  /** All fields ready — the single Activate button can be enabled. */
  const canActivate =
    apiKey.trim().length >= 8 &&
    numbers.length > 0 &&
    selectedNumberId !== null &&
    webhookSecret.trim().length > 0 &&
    !isValidating &&
    !isActivating;

  return {
    apiKey,
    setApiKey,
    numbers,
    selectedNumberId,
    setSelectedNumberId,
    webhookSecret,
    setWebhookSecret,
    isValidating,
    isActivating,
    activated,
    canActivate,
    error,
    validateKey,
    activate,
    reset,
  };
}
