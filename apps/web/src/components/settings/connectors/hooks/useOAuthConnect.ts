/**
 * Generic OAuth connection hook.
 * Parameterized by auth endpoint mapping to support Google, Microsoft, and future providers.
 */

import { useCallback } from 'react';
import apiClient from '@/lib/api-client';
import { logger } from '@/lib/logger';

interface UseOAuthConnectOptions {
  onError?: (error: string) => void;
}

interface UseOAuthConnectReturn {
  /**
   * Initiate OAuth flow for a connector type.
   * Redirects to provider OAuth authorization URL.
   */
  connect: (connectorType: string) => Promise<void>;
}

export function useOAuthConnect(
  authEndpoints: Record<string, string>,
  componentName: string,
  { onError }: UseOAuthConnectOptions = {},
): UseOAuthConnectReturn {
  const connect = useCallback(
    async (connectorType: string) => {
      const endpoint = authEndpoints[connectorType];

      if (!endpoint) {
        const errorMsg = `No OAuth endpoint configured for connector: ${connectorType}`;
        logger.error(errorMsg, new Error(errorMsg), {
          component: componentName,
          connectorType,
        });
        onError?.(errorMsg);
        return;
      }

      try {
        const response = await apiClient.get<{ authorization_url: string }>(endpoint);
        window.location.href = response.authorization_url;
      } catch (error: unknown) {
        const apiError = error as { response?: { data?: { detail?: string } } };
        const errorDetail = apiError.response?.data?.detail || 'Failed to initiate OAuth';

        logger.error(`Failed to initiate ${connectorType} OAuth`, error as Error, {
          component: componentName,
          endpoint,
          connectorType,
          errorDetail,
        });

        onError?.(errorDetail);
      }
    },
    [authEndpoints, componentName, onError]
  );

  return { connect };
}
