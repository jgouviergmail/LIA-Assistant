'use client';

import { useCallback, useEffect, useRef, useState } from 'react';

import { apiClient, ApiError } from '@/lib/api-client';
import { logger } from '@/lib/logger';
import type { UserUsageLimitResponse } from '@/types/usage-limits';

const POLLING_INTERVAL_MS = 60_000; // 60 seconds

export interface UseUsageLimitsReturn {
  /** Full usage limits response from API */
  limits: UserUsageLimitResponse | null;
  /** Whether the user is blocked (any reason) */
  isBlocked: boolean;
  /** Reason for blocking (if blocked) */
  blockReason: string | null;
  /** Loading state (true only on initial load) */
  isLoading: boolean;
  /** Manually trigger a refresh */
  refetch: () => Promise<void>;
}

/**
 * Hook to fetch and poll the current user's usage limits.
 *
 * Handles 404 gracefully (feature disabled → returns null limits).
 * Auto-refreshes every 60 seconds.
 */
export function useUsageLimits(): UseUsageLimitsReturn {
  const [limits, setLimits] = useState<UserUsageLimitResponse | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const featureDisabledRef = useRef(false);
  const intervalRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const fetchLimits = useCallback(async () => {
    if (featureDisabledRef.current) return;

    try {
      const response = await apiClient.get<UserUsageLimitResponse>('/usage-limits/me');
      setLimits(response);
    } catch (err) {
      if (err instanceof ApiError && err.status === 404) {
        // Feature disabled (router not registered) — stop polling
        featureDisabledRef.current = true;
        setLimits(null);
        if (intervalRef.current) {
          clearInterval(intervalRef.current);
          intervalRef.current = null;
        }
        return;
      }
      logger.error('Failed to fetch usage limits', err as Error, {
        component: 'useUsageLimits',
      });
    } finally {
      setIsLoading(false);
    }
  }, []); // No dependencies — uses refs for mutable state

  // Initial fetch + polling
  useEffect(() => {
    fetchLimits();

    intervalRef.current = setInterval(fetchLimits, POLLING_INTERVAL_MS);

    return () => {
      if (intervalRef.current) {
        clearInterval(intervalRef.current);
        intervalRef.current = null;
      }
    };
  }, [fetchLimits]);

  return {
    limits,
    isBlocked: limits?.is_blocked ?? false,
    blockReason: limits?.blocked_reason ?? null,
    isLoading,
    refetch: fetchLimits,
  };
}
