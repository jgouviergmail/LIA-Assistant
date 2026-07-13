'use client';

/**
 * Telephony (ElevenLabs) connector wizard.
 *
 * Multi-step BYO flow: paste API key → validate + pick number → configure the
 * post-call webhook (URL + HMAC secret) → activate. Calls are billed on the
 * user's own ElevenLabs/telephony accounts (D-9) — surfaced as a notice.
 */

import { Check, Copy, KeyRound, Loader2, Phone } from 'lucide-react';
import { useState } from 'react';
import { useTranslation } from 'react-i18next';

import type { Language } from '@/i18n/settings';

import { buildTelephonyWebhookUrl, useTelephony } from './hooks/useTelephony';

interface TelephonyConnectorFormProps {
  lng: Language;
  onSuccess?: () => void;
  onCancel?: () => void;
}

export function TelephonyConnectorForm({
  lng: _lng,
  onSuccess,
  onCancel,
}: TelephonyConnectorFormProps) {
  const { t } = useTranslation();
  const {
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
  } = useTelephony({ onSuccess });

  const [copied, setCopied] = useState(false);
  const webhookUrl = buildTelephonyWebhookUrl();

  const copyWebhookUrl = () => {
    void navigator.clipboard?.writeText(webhookUrl).then(() => {
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    });
  };

  return (
    <div className="space-y-4">
      {/* Billing notice (always visible while configuring) */}
      {step !== 'success' && (
        <div className="rounded-lg bg-amber-50 p-3 text-xs text-amber-700 dark:bg-amber-900/20 dark:text-amber-400">
          {t('settings.connectors.telephony.billing_notice')}
        </div>
      )}

      {/* Step 1: API key */}
      {step === 'key' && (
        <div className="space-y-3">
          <h4 className="text-sm font-medium text-gray-700 dark:text-gray-300">
            {t('settings.connectors.telephony.step_key')}
          </h4>
          <div className="relative">
            <KeyRound className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-gray-400" />
            <input
              type="password"
              value={apiKey}
              onChange={e => setApiKey(e.target.value)}
              placeholder={t('settings.connectors.telephony.key_placeholder')}
              className="w-full rounded-lg border border-gray-200 py-2 pl-9 pr-3 text-sm dark:border-gray-700 dark:bg-gray-800"
            />
          </div>
          <button
            onClick={validateKey}
            disabled={isLoading || apiKey.trim().length < 8}
            className="flex w-full items-center justify-center rounded-lg bg-indigo-500 px-4 py-2 text-sm font-medium text-white transition-colors hover:bg-indigo-600 disabled:opacity-50"
          >
            {isLoading ? (
              <Loader2 className="h-4 w-4 animate-spin" />
            ) : (
              t('settings.connectors.telephony.validate_key')
            )}
          </button>
        </div>
      )}

      {/* Step 2: pick a number */}
      {step === 'number' && (
        <div className="space-y-3">
          <h4 className="text-sm font-medium text-gray-700 dark:text-gray-300">
            {t('settings.connectors.telephony.step_number')}
          </h4>
          {numbers.map(number => (
            <button
              key={number.phone_number_id}
              onClick={() => setSelectedNumberId(number.phone_number_id)}
              className={`flex w-full items-center gap-3 rounded-lg border p-3 text-left transition-colors ${
                selectedNumberId === number.phone_number_id
                  ? 'border-indigo-400 bg-indigo-50 dark:bg-indigo-900/20'
                  : 'border-gray-200 hover:bg-gray-50 dark:border-gray-700 dark:hover:bg-gray-800'
              }`}
            >
              <Phone className="h-5 w-5 text-indigo-500" />
              <div>
                <div className="text-sm font-medium">{number.phone_number}</div>
                {number.provider && (
                  <div className="text-xs text-gray-500">{number.provider}</div>
                )}
              </div>
            </button>
          ))}
          {selectedNumberId && (
            <button
              onClick={() => setStep('webhook')}
              className="w-full rounded-lg bg-indigo-500 px-4 py-2 text-sm font-medium text-white transition-colors hover:bg-indigo-600"
            >
              {t('common.next')}
            </button>
          )}
        </div>
      )}

      {/* Step 3: webhook URL + secret */}
      {step === 'webhook' && (
        <div className="space-y-3">
          <h4 className="text-sm font-medium text-gray-700 dark:text-gray-300">
            {t('settings.connectors.telephony.step_webhook')}
          </h4>
          <p className="text-xs text-gray-500">
            {t('settings.connectors.telephony.webhook_instructions')}
          </p>
          <div className="flex items-center gap-2 rounded-lg border border-gray-200 bg-gray-50 p-2 dark:border-gray-700 dark:bg-gray-800">
            <code className="flex-1 truncate text-xs text-gray-700 dark:text-gray-300">
              {webhookUrl}
            </code>
            <button
              onClick={copyWebhookUrl}
              className="shrink-0 rounded p-1 text-gray-500 hover:bg-gray-200 dark:hover:bg-gray-700"
              aria-label={t('settings.connectors.telephony.copy_url')}
            >
              {copied ? (
                <Check className="h-4 w-4 text-green-500" />
              ) : (
                <Copy className="h-4 w-4" />
              )}
            </button>
          </div>
          <input
            type="password"
            value={webhookSecret}
            onChange={e => setWebhookSecret(e.target.value)}
            placeholder={t('settings.connectors.telephony.secret_placeholder')}
            className="w-full rounded-lg border border-gray-200 px-3 py-2 text-sm dark:border-gray-700 dark:bg-gray-800"
          />
          <button
            onClick={activate}
            disabled={isLoading || webhookSecret.trim().length < 1}
            className="flex w-full items-center justify-center rounded-lg bg-indigo-500 px-4 py-2 text-sm font-medium text-white transition-colors hover:bg-indigo-600 disabled:opacity-50"
          >
            {isLoading ? (
              <Loader2 className="h-4 w-4 animate-spin" />
            ) : (
              t('settings.connectors.telephony.activate')
            )}
          </button>
        </div>
      )}

      {/* Step 4: success */}
      {step === 'success' && (
        <div className="space-y-3 text-center">
          <div className="mx-auto flex h-16 w-16 items-center justify-center rounded-full bg-green-100 dark:bg-green-900/30">
            <Phone className="h-8 w-8 text-green-500" />
          </div>
          <p className="text-sm font-medium text-green-600">
            {t('settings.connectors.telephony.activated')}
          </p>
        </div>
      )}

      {/* Error display */}
      {error && (
        <div className="rounded-lg bg-red-50 p-3 text-sm text-red-600 dark:bg-red-900/20 dark:text-red-400">
          {error}
        </div>
      )}

      {/* Cancel / Back button */}
      {step !== 'success' && (
        <button
          onClick={step === 'key' ? onCancel : reset}
          className="w-full rounded-lg border border-gray-200 px-4 py-2 text-sm text-gray-600 transition-colors hover:bg-gray-50 dark:border-gray-700 dark:text-gray-400 dark:hover:bg-gray-800"
        >
          {step === 'key' ? t('common.cancel') : t('common.back')}
        </button>
      )}
    </div>
  );
}
