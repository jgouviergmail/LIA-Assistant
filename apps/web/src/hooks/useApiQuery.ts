import { useState, useEffect, useCallback, useRef, useMemo } from 'react';
import apiClient, { ApiError, RequestConfig } from '@/lib/api-client';
import type { QueryParamValue } from '@/lib/api-client';
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
  params?: Record<string, QueryParamValue>;
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

/** Normalize and report a current request's failure at the API boundary. */
function reportQueryFailure(
  error: Error,
  endpoint: string,
  component: string,
  params: Record<string, QueryParamValue> | undefined
): Error {
  const failure =
    error instanceof ApiError ? error : new Error(error.message || 'Failed to fetch data');
  logger.error(`API query failed: ${endpoint}`, failure, {
    component,
    endpoint,
    params,
    status: error instanceof ApiError ? error.status : undefined,
  });
  return failure;
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
  const activeRequest = useRef<AbortController | null>(null);

  // Use refs for callbacks - synced after every commit (render-phase ref
  // writes are forbidden). The refs are only read on the async fetch path,
  // which always resolves post-commit, so they are current without
  // triggering refetches.
  const onSuccessRef = useRef(onSuccess);
  const onErrorRef = useRef(onError);
  useEffect(() => {
    onSuccessRef.current = onSuccess;
    onErrorRef.current = onError;
  });

  // Memoize params and config by their JSON representation to prevent
  // infinite loops when callers pass inline objects
  const paramsKey = JSON.stringify(params);
  const configKey = JSON.stringify(config);
  const callerSignal = config?.signal;
  // eslint-disable-next-line react-hooks/exhaustive-deps -- paramsKey is the JSON identity of params
  const stableParams = useMemo(() => params, [paramsKey]);
  // eslint-disable-next-line react-hooks/exhaustive-deps -- signal has identity; the other options have JSON identity
  const stableConfig = useMemo(() => config, [configKey, callerSignal]);

  const fetchData = useCallback(
    async (lifetime: AbortSignal) => {
      if (!enabled || lifetime.aborted) return;

      activeRequest.current?.abort();
      const request = new AbortController();
      activeRequest.current = request;
      const signals = [request.signal, lifetime];
      if (stableConfig?.signal) signals.push(stableConfig.signal);
      const signal = AbortSignal.any(signals);

      setLoading(true);
      setError(null);

      try {
        const response = await apiClient.get<T>(endpoint, {
          params: stableParams,
          ...stableConfig,
          signal,
        });

        if (signal.aborted) return;
        setData(response);
        onSuccessRef.current?.(response);
      } catch (err) {
        const error = err as Error;

        // Don't set error for aborted requests
        if (signal.aborted || error.name === 'AbortError') {
          return;
        }

        const errorObj = reportQueryFailure(error, endpoint, componentName, stableParams);
        setError(errorObj);
        onErrorRef.current?.(errorObj);
      } finally {
        // An old request's completion must not hide a newer request's spinner.
        if (activeRequest.current === request) {
          activeRequest.current = null;
          setLoading(false);
        }
      }
    },
    [endpoint, componentName, enabled, stableParams, stableConfig]
  );

  const activeEffect = useRef<{
    controller: AbortController;
    read: typeof fetchData;
  } | null>(null);

  // Fetch on mount and when dependencies change
  useEffect(() => {
    const abortController = new AbortController();
    activeEffect.current = { controller: abortController, read: fetchData };
    // Finish synchronous effect setup/cleanup before doing external IO. The
    // Strict Mode probe (or an immediate unmount) then cancels an unsent read,
    // rather than aborting a request the server may already be handling.
    queueMicrotask(() => {
      void fetchData(abortController.signal);
    });

    return () => {
      abortController.abort();
      activeRequest.current?.abort();
      activeRequest.current = null;
      activeEffect.current = null;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps -- deps spread is intentional for dynamic dependencies
  }, [fetchData, ...deps]);

  // A mutation may retain this callback across a navigation or an unmount.
  // It must not restart the old query or cancel the new screen's read.
  const refetch = useCallback(() => {
    const effect = activeEffect.current;
    return effect?.read === fetchData ? fetchData(effect.controller.signal) : Promise.resolve();
  }, [fetchData]);

  return {
    data,
    loading: enabled && loading,
    error,
    refetch,
    setData,
  };
}
