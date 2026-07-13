/**
 * Hook for the per-user telephony (ElevenLabs) connector wizard.
 *
 * Multi-step BYO flow (spec §4.2):
 * 1. key      — paste the ElevenLabs API key → validate + list workspace numbers
 * 2. number   — pick the number LIA will call from
 * 3. webhook  — show LIA's post-call webhook URL + paste the workspace HMAC secret
 * 4. success  — the guardrailed agent is provisioned and the connector is active
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

export type TelephonyStep = 'key' | 'number' | 'webhook' | 'success';

/** Public URL the user pastes into their ElevenLabs workspace webhook config. */
export function buildTelephonyWebhookUrl(): string {
  const apiBaseUrl = process.env.NEXT_PUBLIC_API_URL || '';
  return `${apiBaseUrl}/api/v1/telephony/webhook`;
}

export function useTelephony({ onSuccess, onError }: UseTelephonyOptions = {}) {
  const { t } = useTranslation();
  const [step, setStep] = useState<TelephonyStep>('key');
  const [apiKey, setApiKey] = useState('');
  const [numbers, setNumbers] = useState<TelephonyPhoneNumber[]>([]);
  const [selectedNumberId, setSelectedNumberId] = useState<string | null>(null);
  const [webhookSecret, setWebhookSecret] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const validateKey = useCallback(async () => {
    setIsLoading(true);
    setError(null);
    try {
      const data = await apiClient.post<ValidateKeyResponse>(
        '/telephony/connector/validate-key',
        { api_key: apiKey }
      );
      if (!data.is_valid) {
        setError(t('settings.connectors.telephony.invalid_key'));
        return;
      }
      setNumbers(data.numbers || []);
      if (!data.numbers || data.numbers.length === 0) {
        setError(t('settings.connectors.telephony.no_numbers'));
        return;
      }
      setStep('number');
    } catch (err) {
      const msg = err instanceof Error ? err.message : 'Validation failed';
      logger.error('Telephony key validation failed', err as Error, {
        component: 'useTelephony',
      });
      setError(msg);
      onError?.(msg);
    } finally {
      setIsLoading(false);
    }
  }, [apiKey, t, onError]);

  const activate = useCallback(async () => {
    if (!selectedNumberId) return;
    setIsLoading(true);
    setError(null);
    try {
      const selected = numbers.find(n => n.phone_number_id === selectedNumberId);
      await apiClient.post<ActivateResponse>('/telephony/connector/activate', {
        api_key: apiKey,
        agent_phone_number_id: selectedNumberId,
        webhook_secret: webhookSecret,
        caller_number_display: selected?.phone_number ?? null,
      });
      setStep('success');
      onSuccess?.();
    } catch (err) {
      const msg = err instanceof Error ? err.message : 'Activation failed';
      logger.error('Telephony activation failed', err as Error, { component: 'useTelephony' });
      setError(msg);
      onError?.(msg);
    } finally {
      setIsLoading(false);
    }
  }, [apiKey, selectedNumberId, webhookSecret, numbers, onSuccess, onError]);

  const reset = useCallback(() => {
    setStep('key');
    setApiKey('');
    setNumbers([]);
    setSelectedNumberId(null);
    setWebhookSecret('');
    setError(null);
    setIsLoading(false);
  }, []);

  return {
    step,
    setStep,
    apiKey,
    setApiKey,
    numbers,
    selectedNumberId,
    setSelectedNumberId,
    webhookSecret,
    setWebhookSecret,
    isLoading,
    error,
    validateKey,
    activate,
    reset,
  };
}
