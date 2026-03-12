import { useState, useEffect, useCallback, useRef, useMemo } from 'react';
import apiClient, { ApiError, RequestConfig } from '@/lib/api-client';
import { logger } from '@/lib/logger';

/**
 * Generic hook for fetching data from an API endpoint with loading and error states.
 *
 * Features:
 * - Automatic fetch on mount
 * - Loading and error state management
 * - Stable refetch function (won't cause re-renders)
 * - Callbacks (onSuccess, onError) don't trigger refetches
 * - params and config are deep-compared to prevent infinite loops
 *
 * @template T - The type of data returned by the API
 * @param endpoint - The API endpoint to fetch from
 * @param options - Configuration options
 * @returns Object containing data, loading state, error, and refetch function
 *
 * @example
 * ```tsx
 * const { data, loading, error, refetch } = useApiQuery<User[]>('/users', {
 *   componentName: 'UserList',
 *   initialData: [],
 * });
 * ```
 */
export interface UseApiQueryOptions<T> {
  /** Component name for logging */
  componentName: string;
  /** Initial data value */
  initialData?: T;
  /** Whether to fetch on mount (default: true) */
  enabled?: boolean;
  /** Request parameters */
  params?: Record<string, string | number | boolean>;
  /** Additional request config */
  config?: RequestConfig;
  /** Callback on success */
  onSuccess?: (data: T) => void;
  /** Callback on error */
  onError?: (error: Error) => void;
  /** Dependencies for refetching */
  deps?: unknown[];
}

export interface UseApiQueryResult<T> {
  /** The fetched data */
  data: T | undefined;
  /** Loading state */
  loading: boolean;
  /** Error if fetch failed */
  error: Error | null;
  /** Function to manually refetch */
  refetch: () => Promise<void>;
  /** Function to update data directly */
  setData: React.Dispatch<React.SetStateAction<T | undefined>>;
}

export function useApiQuery<T = unknown>(
  endpoint: string,
  options: UseApiQueryOptions<T>
): UseApiQueryResult<T> {
  // Defensive check for runtime issues (incorrect usage, bad builds)
  if (!options) {
    throw new Error(
      `useApiQuery: options is required. Got endpoint="${endpoint}". ` +
        'Make sure to call useApiQuery(endpoint, options) with two arguments.'
    );
  }

  const {
    componentName,
    initialData,
    enabled = true,
    params,
    config,
    onSuccess,
    onError,
    deps = [],
  } = options;

  const [data, setData] = useState<T | undefined>(initialData);
  const [loading, setLoading] = useState<boolean>(enabled);
  const [error, setError] = useState<Error | null>(null);

  // Use refs for callbacks - updated synchronously each render
  // This ensures callbacks are always current without triggering refetches
  const onSuccessRef = useRef(onSuccess);
  const onErrorRef = useRef(onError);
  onSuccessRef.current = onSuccess;
  onErrorRef.current = onError;

  // Memoize params and config by their JSON representation to prevent
  // infinite loops when callers pass inline objects
  // eslint-disable-next-line react-hooks/exhaustive-deps
  const stableParams = useMemo(() => params, [JSON.stringify(params)]);
  // eslint-disable-next-line react-hooks/exhaustive-deps
  const stableConfig = useMemo(() => config, [JSON.stringify(config)]);

  const fetchData = useCallback(
    async (signal?: AbortSignal) => {
      if (!enabled) return;

      setLoading(true);
      setError(null);

      try {
        const response = await apiClient.get<T>(endpoint, {
          params: stableParams,
          signal,
          ...stableConfig,
        });

        setData(response);
        onSuccessRef.current?.(response);
      } catch (err) {
        const error = err as Error;

        // Don't set error for aborted requests
        if (error.name === 'AbortError') {
          return;
        }

        const errorObj =
          error instanceof ApiError ? error : new Error(error.message || 'Failed to fetch data');

        setError(errorObj);

        logger.error(`API query failed: ${endpoint}`, errorObj, {
          component: componentName,
          endpoint,
          params: stableParams,
          status: error instanceof ApiError ? error.status : undefined,
        });

        onErrorRef.current?.(errorObj);
      } finally {
        setLoading(false);
      }
    },
    [endpoint, componentName, enabled, stableParams, stableConfig]
  );

  // Fetch on mount and when dependencies change
  useEffect(() => {
    const abortController = new AbortController();
    fetchData(abortController.signal);

    return () => {
      abortController.abort();
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps -- deps spread is intentional for dynamic dependencies
  }, [fetchData, ...deps]);

  // Stable refetch function that doesn't change between renders
  const refetch = useCallback(() => fetchData(), [fetchData]);

  return {
    data,
    loading,
    error,
    refetch,
    setData,
  };
}
