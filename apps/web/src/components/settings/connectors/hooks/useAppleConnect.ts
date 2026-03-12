/**
 * Hook for Apple iCloud connection.
 * Handles credential validation and multi-service activation.
 */

import { useCallback, useState } from 'react';
import apiClient from '@/lib/api-client';
import { logger } from '@/lib/logger';

interface AppleActivationResponse {
  activated: Array<{ id: string; connector_type: string; status: string }>;
  deactivated: Array<{ id: string; connector_type: string; status: string }>;
}

interface UseAppleConnectOptions {
  onError?: (error: string) => void;
  onSuccess?: () => void;
}

interface UseAppleConnectReturn {
  /** Validate credentials and activate Apple iCloud services in one step */
  connect: (
    appleId: string,
    appPassword: string,
    services: string[]
  ) => Promise<AppleActivationResponse | null>;
  /** Whether a connection is in progress */
  connecting: boolean;
}

export function useAppleConnect({
  onError,
  onSuccess,
}: UseAppleConnectOptions = {}): UseAppleConnectReturn {
  const [connecting, setConnecting] = useState(false);

  const connect = useCallback(
    async (
      appleId: string,
      appPassword: string,
      services: string[]
    ): Promise<AppleActivationResponse | null> => {
      setConnecting(true);
      try {
        const response = await apiClient.post<AppleActivationResponse>(
          '/connectors/apple/activate',
          {
            apple_id: appleId,
            app_password: appPassword,
            services,
          }
        );
        onSuccess?.();
        return response;
      } catch (error: unknown) {
        const apiError = error as { response?: { data?: { detail?: string } } };
        const errorDetail =
          apiError.response?.data?.detail || 'Failed to connect Apple services';
        logger.error('Apple connection failed', error as Error, {
          component: 'useAppleConnect',
          services,
        });
        onError?.(errorDetail);
        return null;
      } finally {
        setConnecting(false);
      }
    },
    [onError, onSuccess]
  );

  return { connect, connecting };
}
