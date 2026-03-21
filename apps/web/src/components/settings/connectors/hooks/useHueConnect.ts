/**
 * Hook for Philips Hue Bridge connection management.
 *
 * Handles the multi-step connection flow:
 * - Mode selection (local vs remote)
 * - Bridge discovery on local network
 * - Press-link pairing with countdown timer
 * - Local activation after pairing
 * - Remote OAuth2 redirect
 */

import { useCallback, useEffect, useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';
import apiClient from '@/lib/api-client';
import { logger } from '@/lib/logger';

interface HueBridgeInfo {
  id: string;
  internalipaddress: string;
  port?: number;
}

interface HuePairingResponse {
  success: boolean;
  application_key?: string;
  client_key?: string;
  bridge_id?: string;
  error?: string;
}

interface HueDiscoveryResponse {
  bridges: HueBridgeInfo[];
}

interface UseHueConnectOptions {
  onSuccess?: () => void;
  onError?: (error: string) => void;
}

type HueStep = 'mode' | 'discover' | 'pair' | 'success';

export function useHueConnect({ onSuccess, onError }: UseHueConnectOptions = {}) {
  const { t } = useTranslation();
  const [step, setStep] = useState<HueStep>('mode');
  const [bridges, setBridges] = useState<HueBridgeInfo[]>([]);
  const [selectedBridge, setSelectedBridge] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [isPairing, setIsPairing] = useState(false);
  const [countdown, setCountdown] = useState(30);
  const [error, setError] = useState<string | null>(null);
  const countdownRef = useRef<ReturnType<typeof setInterval> | null>(null);

  // Cleanup countdown on unmount
  useEffect(() => {
    return () => {
      if (countdownRef.current) {
        clearInterval(countdownRef.current);
      }
    };
  }, []);

  const discoverBridges = useCallback(async () => {
    setIsLoading(true);
    setError(null);
    try {
      const data = await apiClient.post<HueDiscoveryResponse>(
        '/connectors/philips-hue/discover'
      );
      setBridges(data.bridges || []);
      if (data.bridges?.length > 0) {
        setStep('discover');
      } else {
        setError(t('settings.connectors.hue.no_bridges_found'));
      }
    } catch (err) {
      const msg = err instanceof Error ? err.message : 'Discovery failed';
      logger.error('Hue bridge discovery failed', err as Error, { component: 'useHueConnect' });
      setError(msg);
      onError?.(msg);
    } finally {
      setIsLoading(false);
    }
  }, [t, onError]);

  const startPairing = useCallback(() => {
    setStep('pair');
    setCountdown(30);
    countdownRef.current = setInterval(() => {
      setCountdown((prev) => {
        if (prev <= 1) {
          if (countdownRef.current) clearInterval(countdownRef.current);
          return 0;
        }
        return prev - 1;
      });
    }, 1000);
  }, []);

  const pairBridge = useCallback(
    async (bridgeIp: string) => {
      setIsPairing(true);
      setError(null);
      try {
        const pairData = await apiClient.post<HuePairingResponse>(
          '/connectors/philips-hue/pair',
          { bridge_ip: bridgeIp }
        );

        if (pairData.success) {
          // Activate connector
          await apiClient.post('/connectors/philips-hue/activate/local', {
            bridge_ip: bridgeIp,
            application_key: pairData.application_key,
            client_key: pairData.client_key,
            bridge_id: pairData.bridge_id,
          });

          if (countdownRef.current) clearInterval(countdownRef.current);
          setStep('success');
          onSuccess?.();
        } else {
          setError(pairData.error || t('settings.connectors.hue.pairing_error'));
        }
      } catch (err) {
        const msg = err instanceof Error ? err.message : 'Pairing failed';
        logger.error('Hue pairing failed', err as Error, { component: 'useHueConnect' });
        setError(msg);
        onError?.(msg);
      } finally {
        setIsPairing(false);
      }
    },
    [t, onSuccess, onError]
  );

  const connectRemote = useCallback(async () => {
    setIsLoading(true);
    try {
      const data = await apiClient.get<{ authorization_url: string }>(
        '/connectors/philips-hue/authorize'
      );
      if (data.authorization_url) {
        window.location.href = data.authorization_url;
      }
    } catch (err) {
      const msg = err instanceof Error ? err.message : 'OAuth initiation failed';
      logger.error('Hue OAuth initiation failed', err as Error, { component: 'useHueConnect' });
      setError(msg);
      onError?.(msg);
    } finally {
      setIsLoading(false);
    }
  }, [onError]);

  const reset = useCallback(() => {
    setStep('mode');
    setBridges([]);
    setSelectedBridge(null);
    setError(null);
    setCountdown(30);
    if (countdownRef.current) clearInterval(countdownRef.current);
  }, []);

  return {
    step,
    bridges,
    selectedBridge,
    isLoading,
    isPairing,
    countdown,
    error,
    setStep,
    setSelectedBridge,
    discoverBridges,
    startPairing,
    pairBridge,
    connectRemote,
    reset,
  };
}
