import { useState, useEffect, useCallback } from 'react';
import { useAuth } from '@/hooks/useAuth';
import { logger } from '@/lib/logger';
import { useLoggingContext } from '@/lib/logging-context';

/**
 * User token usage and cost statistics
 */
export interface UserStatistics {
  // Lifetime totals
  /** ISO datetime — start of the lifetime totals (user's account creation date) */
  total_since: string;
  total_prompt_tokens: number;
  total_completion_tokens: number;
  total_cached_tokens: number;
  total_cost_eur: number;
  total_messages: number;
  total_google_api_requests: number;
  total_google_api_cost_eur: number;

  // Current billing cycle
  current_cycle_start: string; // ISO date
  cycle_prompt_tokens: number;
  cycle_completion_tokens: number;
  cycle_cached_tokens: number;
  cycle_cost_eur: number;
  cycle_messages: number;
  cycle_google_api_requests: number;
  cycle_google_api_cost_eur: number;
}

export interface UseUserStatisticsReturn {
  statistics: UserStatistics | null;
  isLoading: boolean;
  error: string | null;
  refetch: () => Promise<void>;
}

/**
 * Hook to fetch and auto-refresh user token usage statistics
 * Refreshes every 30 seconds automatically
 */
export const useUserStatistics = (): UseUserStatisticsReturn => {
  const { user } = useAuth();
  const { withContext } = useLoggingContext();
  const [statistics, setStatistics] = useState<UserStatistics | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const fetchStatistics = useCallback(async () => {
    if (!user) {
      setIsLoading(false);
      return;
    }

    try {
      const API_BASE_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';
      const response = await fetch(`${API_BASE_URL}/api/v1/chat/users/me/statistics`, {
        method: 'GET',
        credentials: 'include', // Send session cookie
        headers: {
          'Content-Type': 'application/json',
        },
      });

      if (!response.ok) {
        throw new Error(`Failed to fetch statistics: ${response.status} ${response.statusText}`);
      }

      const data = await response.json();
      setStatistics(data);
      setError(null);

      logger.debug(
        'user_statistics_fetched',
        withContext({
          component: 'useUserStatistics',
          totalMessages: data.total_messages,
          cycleMessages: data.cycle_messages,
        })
      );
    } catch (err) {
      const errorMessage = err instanceof Error ? err.message : 'Unknown error';
      setError(errorMessage);
      logger.error(
        'user_statistics_fetch_error',
        err as Error,
        withContext({
          component: 'useUserStatistics',
        })
      );
    } finally {
      setIsLoading(false);
    }
  }, [user, withContext]);

  // Initial fetch
  useEffect(() => {
    fetchStatistics();
  }, [fetchStatistics]);

  // Auto-refresh every 30 seconds
  useEffect(() => {
    if (!user) return;

    const interval = setInterval(() => {
      fetchStatistics();
    }, 30000); // 30 seconds

    return () => clearInterval(interval);
  }, [user, fetchStatistics]);

  return {
    statistics,
    isLoading,
    error,
    refetch: fetchStatistics,
  };
};
