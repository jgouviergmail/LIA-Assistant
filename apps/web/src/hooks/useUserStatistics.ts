import { useState, useEffect, useCallback } from 'react';
import { useAuth } from '@/hooks/useAuth';
import apiClient from '@/lib/api-client';
import { logger } from '@/lib/logger';
import { useLoggingContext } from '@/lib/logging-context';
import { useStaleGuard } from '@/hooks/useStaleGuard';

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
  // Staleness guard (audit F037): drop out-of-order poll responses and never
  // commit state after unmount — shared, tested helper (useStaleGuard).
  const guard = useStaleGuard();

  const fetchStatistics = useCallback(async () => {
    // Claim a request id up-front so `isStale()` guards EVERY exit — including the
    // finally below: only the current request (not a superseded one) may clear
    // loading, otherwise an older poll finishing first cuts the newer one's
    // loading state (audit F037).
    const isStale = guard.begin();

    if (!user) {
      if (!isStale()) setIsLoading(false);
      return;
    }

    try {
      // Through `apiClient`, like every other data call: an expired session
      // must eject to the localized login rather than leave the statistics
      // panel showing a bare "Failed to fetch statistics: 401".
      const data = await apiClient.get<UserStatistics>('/chat/users/me/statistics');
      if (isStale()) return;
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
      if (isStale()) return;
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
      if (!isStale()) {
        setIsLoading(false);
      }
    }
  }, [user, withContext, guard]);

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
