'use client';

/**
 * Logging Context Provider
 *
 * Provides global logging context (userId, sessionId, traceId) to the logger
 * This context is automatically injected into all log statements
 *
 * Usage:
 * ```tsx
 * // In root layout
 * <LoggingProvider userId={user?.id} sessionId={sessionId}>
 *   {children}
 * </LoggingProvider>
 *
 * // In any component
 * import { useLoggingContext } from '@/lib/logging-context'
 *
 * const { withContext } = useLoggingContext()
 * logger.info('user_action', withContext({ action: 'click_button' }))
 * ```
 */

import { createContext, useContext, useMemo, type ReactNode } from 'react';
import type { LogContext } from './logger';

interface LoggingContextValue {
  userId?: string;
  sessionId?: string;
  traceId?: string;
  /**
   * Merge provided context with global context
   */
  withContext: (context?: LogContext) => LogContext;
}

const LoggingContext = createContext<LoggingContextValue | undefined>(undefined);

interface LoggingProviderProps {
  children: ReactNode;
  userId?: string;
  sessionId?: string;
  traceId?: string;
}

/**
 * Generate a simple trace ID for request tracking
 */
function generateTraceId(): string {
  return `trace_${Date.now()}_${Math.random().toString(36).substring(2, 9)}`;
}

export function LoggingProvider({
  children,
  userId,
  sessionId,
  traceId: providedTraceId,
}: LoggingProviderProps) {
  // Generate trace ID once per mount (per page load)
  const traceId = useMemo(() => providedTraceId || generateTraceId(), [providedTraceId]);

  const value = useMemo<LoggingContextValue>(
    () => ({
      userId,
      sessionId,
      traceId,
      withContext: (context?: LogContext): LogContext => ({
        userId,
        sessionId,
        traceId,
        ...context,
      }),
    }),
    [userId, sessionId, traceId]
  );

  return <LoggingContext.Provider value={value}>{children}</LoggingContext.Provider>;
}

/**
 * Hook to access logging context
 *
 * @throws Error if used outside LoggingProvider
 */
export function useLoggingContext(): LoggingContextValue {
  const context = useContext(LoggingContext);

  if (!context) {
    // Fallback: return a default context instead of throwing
    // This allows components to work even without the provider
    return {
      withContext: (context?: LogContext): LogContext => ({
        ...context,
      }),
    };
  }

  return context;
}
