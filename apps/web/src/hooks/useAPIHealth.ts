/**
 * API Health Check Hook
 *
 * Monitors the health status of the backend API (agent graph service).
 * Checks on mount and when user changes.
 *
 * Extracted from useChat.ts for better separation of concerns.
 */

import { useState, useCallback, useEffect } from 'react';
import { logger } from '@/lib/logger';
import { useLoggingContext } from '@/lib/logging-context';
import { API_ENDPOINTS } from '@/lib/api-config';

export interface UseAPIHealthOptions {
  /** User object - health check only runs when user is authenticated */
  user: { id: string } | null;
  /** Optional callback when health status changes */
  onStatusChange?: (available: boolean) => void;
}

export interface UseAPIHealthReturn {
  /** Whether the API is available and healthy */
  apiAvailable: boolean;
  /** Manually trigger a health check */
  checkHealth: () => Promise<boolean>;
  /** Whether a health check is currently in progress */
  isChecking: boolean;
}

/**
 * Hook to monitor API health status.
 *
 * @param options - Configuration options
 * @returns API health state and check function
 *
 * @example
 * ```tsx
 * const { apiAvailable, checkHealth } = useAPIHealth({ user });
 *
 * if (!apiAvailable) {
 *   return <div>Service temporarily unavailable</div>;
 * }
 * ```
 */
export const useAPIHealth = ({
  user,
  onStatusChange,
}: UseAPIHealthOptions): UseAPIHealthReturn => {
  const { withContext } = useLoggingContext();
  const [apiAvailable, setApiAvailable] = useState(false);
  const [isChecking, setIsChecking] = useState(false);

  /**
   * Check API health and update availability status.
   * Returns the health status for programmatic use.
   */
  const checkHealth = useCallback(async (): Promise<boolean> => {
    if (!user) {
      setApiAvailable(false);
      onStatusChange?.(false);
      return false;
    }

    setIsChecking(true);

    try {
      const response = await fetch(API_ENDPOINTS.AGENTS.HEALTH, {
        method: 'GET',
        credentials: 'include', // Send session cookie
        headers: {
          'Content-Type': 'application/json',
        },
      });

      if (response.ok) {
        const data = await response.json();
        // Verify that the graph is compiled and service is healthy
        const isHealthy = data.status === 'healthy' && data.graph_compiled === true;

        setApiAvailable(isHealthy);
        onStatusChange?.(isHealthy);

        logger.info(
          'api_health_check',
          withContext({
            component: 'useAPIHealth',
            available: isHealthy,
            status: data.status,
            graphCompiled: data.graph_compiled,
          })
        );

        return isHealthy;
      } else {
        setApiAvailable(false);
        onStatusChange?.(false);

        logger.warn(
          'api_health_check_failed',
          withContext({
            component: 'useAPIHealth',
            status: response.status,
            statusText: response.statusText,
          })
        );

        return false;
      }
    } catch (error) {
      setApiAvailable(false);
      onStatusChange?.(false);

      logger.error(
        'api_health_check_error',
        error as Error,
        withContext({
          component: 'useAPIHealth',
        })
      );

      return false;
    } finally {
      setIsChecking(false);
    }
  }, [user, withContext, onStatusChange]);

  /**
   * Check API health on mount and when user changes.
   */
  useEffect(() => {
    checkHealth();
  }, [checkHealth]);

  return {
    apiAvailable,
    checkHealth,
    isChecking,
  };
};
