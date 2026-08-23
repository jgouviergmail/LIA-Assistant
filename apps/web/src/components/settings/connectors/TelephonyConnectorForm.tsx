'use client';

/**
 * Telephony (ElevenLabs) connector — single-screen configuration.
 *
 * The whole setup is visible at once: API key, calling number, post-call
 * webhook (URL + HMAC secret), one Activate button. Only the number picker is
 * intrinsically progressive — the workspace numbers can only be listed after
 * the key is validated, so that section enables once "Validate key" succeeds
 * (and preselects when a single number exists). Calls are billed on the user's
 * own ElevenLabs/telephony accounts (D-9) — surfaced as a notice.
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
  } = useTelephony({ onSuccess });

  const [copied, setCopied] = useState(false);
  const webhookUrl = buildTelephonyWebhookUrl();
  const numbersLoaded = numbers.length > 0;

  const copyWebhookUrl = () => {
    void navigator.clipboard?.writeText(webhookUrl).then(() => {
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    });
  };

  if (activated) {
    return (
      <div className="space-y-3 text-center">
        <div className="mx-auto flex h-16 w-16 items-center justify-center rounded-full bg-green-100 dark:bg-green-900/30">
          <Phone className="h-8 w-8 text-green-500" />
        </div>
        <p className="text-sm font-medium text-green-600">
          {t('settings.connectors.telephony.activated')}
        </p>
      </div>
    );
  }

  return (
    <div className="space-y-5">
      {/* Billing notice */}
      <div className="rounded-lg bg-amber-50 p-3 text-xs text-amber-700 dark:bg-amber-900/20 dark:text-amber-400">
        {t('settings.connectors.telephony.billing_notice')}
      </div>

      {/* Section 1 — API key + inline validation */}
      <div className="space-y-2">
        <label
          id="telephony-api-key-label"
          htmlFor="telephony-api-key"
          className="block text-sm font-medium text-gray-700 dark:text-gray-300"
        >
          {t('settings.connectors.telephony.step_key')}
        </label>
        <div className="flex gap-2">
          <div className="relative flex-1">
            <KeyRound className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-gray-400" />
            <input
              id="telephony-api-key"
              aria-labelledby="telephony-api-key-label"
              type="password"
              value={apiKey}
              onChange={e => setApiKey(e.target.value)}
              placeholder={t('settings.connectors.telephony.key_placeholder')}
              className="w-full rounded-lg border border-input bg-background py-2 pl-9 pr-3 text-sm"
            />
          </div>
          {/* aria-label keeps the button named while isValidating swaps its
              visible text for a spinner-only content (audit F012/F045). */}
          <button
            onClick={validateKey}
            disabled={isValidating || apiKey.trim().length < 8}
            aria-label={t('settings.connectors.telephony.validate_key')}
            aria-busy={isValidating}
            className="shrink-0 rounded-lg bg-indigo-500 px-3 py-2 text-sm font-medium text-white transition-colors hover:bg-indigo-600 disabled:opacity-50"
          >
            {isValidating ? (
              <Loader2 className="h-4 w-4 animate-spin" />
            ) : (
              t('settings.connectors.telephony.validate_key')
            )}
          </button>
        </div>
      </div>

      {/* Section 2 — calling number (enables once the key is validated) */}
      <div className="space-y-2">
        <span className="block text-sm font-medium text-gray-700 dark:text-gray-300">
          {t('settings.connectors.telephony.step_number')}
        </span>
        {numbersLoaded ? (
          numbers.map(number => (
            <button
              key={number.phone_number_id}
              onClick={() => setSelectedNumberId(number.phone_number_id)}
              aria-pressed={selectedNumberId === number.phone_number_id}
              className={`flex w-full items-center gap-3 rounded-lg border p-3 text-left transition-colors ${
                selectedNumberId === number.phone_number_id
                  ? 'border-indigo-400 bg-indigo-50 dark:bg-indigo-900/20'
                  : 'border-gray-200 hover:bg-gray-50 dark:border-gray-700 dark:hover:bg-gray-800'
              }`}
            >
              <Phone className="h-5 w-5 text-indigo-500" />
              <div>
                <div className="text-sm font-medium">{number.phone_number}</div>
                {number.provider && <div className="text-xs text-gray-500">{number.provider}</div>}
              </div>
            </button>
          ))
        ) : (
          <p className="rounded-lg border border-dashed border-gray-200 p-3 text-xs text-gray-500 dark:border-gray-700">
            {t('settings.connectors.telephony.numbers_hint')}
          </p>
        )}
      </div>

      {/* Section 3 — post-call webhook (URL visible from the start) */}
      <div className="space-y-2">
        <span className="block text-sm font-medium text-gray-700 dark:text-gray-300">
          {t('settings.connectors.telephony.step_webhook')}
        </span>
        <p className="text-xs text-gray-500">
          {t('settings.connectors.telephony.webhook_instructions')}
        </p>
        <div className="flex items-center gap-2 rounded-lg border border-input bg-muted p-2">
          <code className="flex-1 truncate text-xs text-gray-700 dark:text-gray-300">
            {webhookUrl}
          </code>
          <button
            onClick={copyWebhookUrl}
            className="shrink-0 rounded p-1 text-gray-500 hover:bg-gray-200 dark:hover:bg-gray-700"
            aria-label={t('settings.connectors.telephony.copy_url')}
          >
            {copied ? <Check className="h-4 w-4 text-green-500" /> : <Copy className="h-4 w-4" />}
          </button>
        </div>
        <label
          id="telephony-webhook-secret-label"
          htmlFor="telephony-webhook-secret"
          className="block text-xs font-medium text-gray-600 dark:text-gray-400"
        >
          {t('settings.connectors.telephony.secret_label')}
        </label>
        <input
          id="telephony-webhook-secret"
          aria-labelledby="telephony-webhook-secret-label"
          type="password"
          value={webhookSecret}
          onChange={e => setWebhookSecret(e.target.value)}
          placeholder={t('settings.connectors.telephony.secret_placeholder')}
          className="w-full rounded-lg border border-input bg-background px-3 py-2 text-sm"
        />
      </div>

      {/* Single Activate button */}
      {/* aria-label: same named-while-busy rationale as the validate button. */}
      <button
        onClick={activate}
        disabled={!canActivate}
        aria-label={t('settings.connectors.telephony.activate')}
        aria-busy={isActivating}
        className="flex w-full items-center justify-center rounded-lg bg-indigo-500 px-4 py-2 text-sm font-medium text-white transition-colors hover:bg-indigo-600 disabled:opacity-50"
      >
        {isActivating ? (
          <Loader2 className="h-4 w-4 animate-spin" />
        ) : (
          t('settings.connectors.telephony.activate')
        )}
      </button>

      {/* Error display */}
      {error && (
        <div className="rounded-lg bg-red-50 p-3 text-sm text-red-600 dark:bg-red-900/20 dark:text-red-400">
          {error}
        </div>
      )}

      {/* Cancel */}
      <button
        onClick={onCancel}
        className="w-full rounded-lg border border-gray-200 px-4 py-2 text-sm text-gray-600 transition-colors hover:bg-gray-50 dark:border-gray-700 dark:text-gray-400 dark:hover:bg-gray-800"
      >
        {t('common.cancel')}
      </button>
    </div>
  );
}
