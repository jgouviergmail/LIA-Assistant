'use client';

import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { useState, type ReactNode } from 'react';

/**
 * Query Client Provider for TanStack Query
 *
 * Configured with optimal defaults:
 * - 5 minute stale time for most queries
 * - 10 minute cache time
 * - No automatic refetch on window focus (prevents unnecessary API calls)
 * - Retry failed requests up to 1 time
 */
export function QueryProvider({ children }: { children: ReactNode }) {
  // Create a client instance per request/session
  // This ensures SSR safety and prevents state sharing between requests
  const [queryClient] = useState(
    () =>
      new QueryClient({
        defaultOptions: {
          queries: {
            // How long data stays fresh before refetch
            staleTime: 5 * 60 * 1000, // 5 minutes
            // How long unused data stays in cache
            gcTime: 10 * 60 * 1000, // 10 minutes (was cacheTime in v4)
            // Don't refetch on window focus (prevents unnecessary API calls)
            refetchOnWindowFocus: false,
            // Don't refetch on mount if data is fresh
            refetchOnMount: false,
            // Retry failed requests once
            retry: 1,
            // Retry delay
            retryDelay: attemptIndex => Math.min(1000 * 2 ** attemptIndex, 30000),
          },
          mutations: {
            // Retry mutations once on failure
            retry: 1,
          },
        },
      })
  );

  return <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>;
}
