import { useState, useCallback } from 'react';
import apiClient, { ApiError, RequestConfig } from '@/lib/api-client';
import { logger } from '@/lib/logger';

/**
 * Generic hook for API mutations (POST, PUT, PATCH, DELETE) with loading and error states.
 *
 * @template TData - The type of data sent to the API
 * @template TResponse - The type of response from the API
 * @param options - Configuration options
 * @returns Object containing mutate function, loading state, error, and reset
 *
 * @example
 * ```tsx
 * const { mutate, loading, error } = useApiMutation<CreateUserData, User>({
 *   method: 'POST',
 *   componentName: 'UserForm',
 *   onSuccess: (user) => {
 *     toast.success(`User ${user.email} created!`);
 *   },
 * });
 *
 * await mutate('/users', { email: 'test@example.com', name: 'Test' });
 * ```
 */
export interface UseApiMutationOptions<TResponse = unknown> {
  /** HTTP method for the mutation */
  method: 'POST' | 'PUT' | 'PATCH' | 'DELETE';
  /** Component name for logging */
  componentName: string;
  /** Additional request config */
  config?: RequestConfig;
  /** Keep a response copy in state. Disable for ephemeral secret delivery. */
  retainResponse?: boolean;
  /** Callback on success */
  onSuccess?: (data: TResponse) => void;
  /** Callback on error */
  onError?: (error: Error) => void;
}

export interface UseApiMutationResult<TData = unknown, TResponse = unknown> {
  /** Function to perform the mutation */
  mutate: (
    endpoint: string,
    data?: TData,
    config?: RequestConfig
  ) => Promise<TResponse | undefined>;
  /** Loading state */
  loading: boolean;
  /** Error if mutation failed */
  error: Error | null;
  /** Function to reset error state */
  reset: () => void;
  /** Response data from last successful mutation */
  data: TResponse | null;
}

async function sendMutation<TData, TResponse>(
  method: UseApiMutationOptions['method'],
  endpoint: string,
  requestData: TData | undefined,
  config?: RequestConfig
): Promise<TResponse> {
  let response;

  switch (method) {
    case 'POST':
      response = await apiClient.post<TResponse>(endpoint, requestData, config);
      break;
    case 'PUT':
      response = await apiClient.put<TResponse>(endpoint, requestData, config);
      break;
    case 'PATCH':
      response = await apiClient.patch<TResponse>(endpoint, requestData, config);
      break;
    case 'DELETE':
      response = await apiClient.delete<TResponse>(endpoint, {
        ...config,
        body: requestData ? JSON.stringify(requestData) : undefined,
      });
      break;
  }

  return response;
}

export function useApiMutation<TData = unknown, TResponse = unknown>(
  options: UseApiMutationOptions<TResponse>
): UseApiMutationResult<TData, TResponse> {
  // Defensive check for runtime issues (hot reload, bad builds)
  if (!options) {
    throw new Error(
      'useApiMutation: options is required. This may indicate a build issue - try clearing the cache.'
    );
  }

  const { method, componentName, config, onSuccess, onError, retainResponse = true } = options;

  const [loading, setLoading] = useState<boolean>(false);
  const [error, setError] = useState<Error | null>(null);
  const [data, setData] = useState<TResponse | null>(null);

  const mutate = useCallback(
    async (
      endpoint: string,
      requestData?: TData,
      requestConfig?: RequestConfig
    ): Promise<TResponse | undefined> => {
      const selectedConfig = requestConfig ? { ...config, ...requestConfig } : config;
      setLoading(true);
      setError(null);

      try {
        const response = await sendMutation<TData, TResponse>(
          method,
          endpoint,
          requestData,
          selectedConfig
        );

        if (retainResponse) setData(response);
        onSuccess?.(response);
        return response;
      } catch (err) {
        if (selectedConfig?.signal?.aborted) throw err;
        const errorObj = err instanceof Error ? err : new Error('Mutation failed');

        setError(errorObj);

        logger.error(`API mutation failed: ${method} ${endpoint}`, errorObj, {
          component: componentName,
          method,
          endpoint,
          status: err instanceof ApiError ? err.status : undefined,
        });

        onError?.(errorObj);
        throw errorObj;
      } finally {
        setLoading(false);
      }
    },
    [method, componentName, config, onSuccess, onError, retainResponse]
  );

  const reset = useCallback(() => {
    setError(null);
    setData(null);
  }, []);

  return {
    mutate,
    loading,
    error,
    reset,
    data,
  };
}
