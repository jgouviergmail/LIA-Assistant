'use client';

/**
 * Philips Hue Bridge pairing form component.
 *
 * Multi-step wizard for connecting a Hue Bridge:
 * 1. Mode selection (local vs remote)
 * 2. Bridge discovery (local mode)
 * 3. Press-link pairing with countdown
 * 4. Success confirmation
 */

import { Lightbulb, Loader2, Radio, Wifi } from 'lucide-react';
import { useTranslation } from 'react-i18next';

import type { Language } from '@/i18n/settings';

import { useHueConnect } from './hooks/useHueConnect';

interface HueBridgePairingFormProps {
  lng: Language;
  onSuccess?: () => void;
  onCancel?: () => void;
}

export function HueBridgePairingForm({
  lng: _lng,
  onSuccess,
  onCancel,
}: HueBridgePairingFormProps) {
  const { t } = useTranslation();
  const {
    step,
    bridges,
    selectedBridge,
    isLoading,
    isPairing,
    countdown,
    error,
    setSelectedBridge,
    discoverBridges,
    startPairing,
    pairBridge,
    connectRemote,
    reset,
  } = useHueConnect({ onSuccess });

  return (
    <div className="space-y-4">
      {/* Step 1: Mode Selection */}
      {step === 'mode' && (
        <div className="space-y-3">
          <h4 className="text-sm font-medium text-gray-700 dark:text-gray-300">
            {t('settings.connectors.hue.mode_select')}
          </h4>

          <button
            onClick={discoverBridges}
            disabled={isLoading}
            className="flex w-full items-center gap-3 rounded-lg border border-gray-200 p-3 text-left transition-colors hover:bg-gray-50 dark:border-gray-700 dark:hover:bg-gray-800"
          >
            <Wifi className="h-5 w-5 text-yellow-500" />
            <div>
              <div className="text-sm font-medium">
                {t('settings.connectors.hue.mode_local')}
              </div>
              <div className="text-xs text-gray-500">
                {t('settings.connectors.hue.mode_local_desc')}
              </div>
            </div>
            {isLoading && <Loader2 className="ml-auto h-4 w-4 animate-spin" />}
          </button>

          <button
            onClick={connectRemote}
            disabled={isLoading}
            className="flex w-full items-center gap-3 rounded-lg border border-gray-200 p-3 text-left transition-colors hover:bg-gray-50 dark:border-gray-700 dark:hover:bg-gray-800"
          >
            <Radio className="h-5 w-5 text-blue-500" />
            <div>
              <div className="text-sm font-medium">
                {t('settings.connectors.hue.mode_remote')}
              </div>
              <div className="text-xs text-gray-500">
                {t('settings.connectors.hue.mode_remote_desc')}
              </div>
            </div>
          </button>
        </div>
      )}

      {/* Step 2: Bridge Discovery */}
      {step === 'discover' && (
        <div className="space-y-3">
          <h4 className="text-sm font-medium text-gray-700 dark:text-gray-300">
            {t('settings.connectors.hue.select_bridge')}
          </h4>

          {bridges.map((bridge) => (
            <button
              key={bridge.id}
              onClick={() => setSelectedBridge(bridge.internalipaddress)}
              className={`flex w-full items-center gap-3 rounded-lg border p-3 text-left transition-colors ${
                selectedBridge === bridge.internalipaddress
                  ? 'border-yellow-400 bg-yellow-50 dark:bg-yellow-900/20'
                  : 'border-gray-200 hover:bg-gray-50 dark:border-gray-700 dark:hover:bg-gray-800'
              }`}
            >
              <Lightbulb className="h-5 w-5 text-yellow-500" />
              <div>
                <div className="text-sm font-medium">{bridge.internalipaddress}</div>
                <div className="text-xs text-gray-500">ID: {bridge.id}</div>
              </div>
            </button>
          ))}

          {selectedBridge && (
            <button
              onClick={startPairing}
              className="w-full rounded-lg bg-yellow-500 px-4 py-2 text-sm font-medium text-white transition-colors hover:bg-yellow-600"
            >
              {t('settings.connectors.hue.press_button')}
            </button>
          )}
        </div>
      )}

      {/* Step 3: Press-Link Pairing */}
      {step === 'pair' && selectedBridge && (
        <div className="space-y-4 text-center">
          <div className="mx-auto flex h-16 w-16 items-center justify-center rounded-full bg-yellow-100 dark:bg-yellow-900/30">
            <Lightbulb className="h-8 w-8 animate-pulse text-yellow-500" />
          </div>

          <div>
            <p className="text-sm font-medium text-gray-700 dark:text-gray-300">
              {t('settings.connectors.hue.press_button')}
            </p>
            <p className="mt-1 text-xs text-gray-500">
              {t('settings.connectors.hue.press_button_desc')}
            </p>
          </div>

          <div className="text-2xl font-bold text-yellow-500">
            {t('settings.connectors.hue.pairing_countdown', {
              seconds: countdown,
            })}
          </div>

          <button
            onClick={() => pairBridge(selectedBridge)}
            disabled={isPairing || countdown === 0}
            className="w-full rounded-lg bg-yellow-500 px-4 py-2 text-sm font-medium text-white transition-colors hover:bg-yellow-600 disabled:opacity-50"
          >
            {isPairing ? (
              <Loader2 className="mx-auto h-4 w-4 animate-spin" />
            ) : (
              t('settings.connectors.hue.pair_button')
            )}
          </button>
        </div>
      )}

      {/* Step 4: Success */}
      {step === 'success' && (
        <div className="space-y-3 text-center">
          <div className="mx-auto flex h-16 w-16 items-center justify-center rounded-full bg-green-100 dark:bg-green-900/30">
            <Lightbulb className="h-8 w-8 text-green-500" />
          </div>
          <p className="text-sm font-medium text-green-600">
            {t('settings.connectors.hue.pairing_success')}
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
          onClick={step === 'mode' ? onCancel : reset}
          className="w-full rounded-lg border border-gray-200 px-4 py-2 text-sm text-gray-600 transition-colors hover:bg-gray-50 dark:border-gray-700 dark:text-gray-400 dark:hover:bg-gray-800"
        >
          {step === 'mode' ? t('common.cancel') : t('common.back')}
        </button>
      )}
    </div>
  );
}
