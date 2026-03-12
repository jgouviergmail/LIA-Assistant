/**
 * Structured Logger for Frontend
 *
 * Provides structured logging with context (userId, sessionId, traceId)
 * Conditional logging based on environment (verbose in dev, critical only in prod)
 * Outputs structured JSON for parsing by observability tools
 *
 * Usage:
 * ```typescript
 * import { logger } from '@/lib/logger'
 *
 * logger.info('user_action', { action: 'login', userId: '123' })
 * logger.error('api_error', error, { endpoint: '/api/users', userId: '123' })
 * ```
 */

export type LogLevel = 'debug' | 'info' | 'warn' | 'error';
export type LogLevelConfig = LogLevel | 'none';

export interface LogContext {
  userId?: string;
  sessionId?: string;
  traceId?: string;
  component?: string;
  action?: string;
  endpoint?: string;
  duration?: number;
  [key: string]: unknown;
}

interface LogEntry {
  timestamp: string;
  level: LogLevel;
  message: string;
  context?: LogContext;
  error?: {
    name: string;
    message: string;
    stack?: string;
  };
}

/**
 * Sensitive fields that should never be logged
 */
const SENSITIVE_FIELDS = [
  'password',
  'token',
  'authorization',
  'cookie',
  'session',
  'secret',
  'apiKey',
  'api_key',
  'access_token',
  'refresh_token',
];

/**
 * Sanitize context to remove sensitive data
 */
function sanitizeContext(context: LogContext): LogContext {
  const sanitized: LogContext = {};

  for (const [key, value] of Object.entries(context)) {
    const lowerKey = key.toLowerCase();

    // Skip sensitive fields
    if (SENSITIVE_FIELDS.some(field => lowerKey.includes(field))) {
      sanitized[key] = '[REDACTED]';
      continue;
    }

    // Recursively sanitize objects
    if (value && typeof value === 'object' && !Array.isArray(value)) {
      sanitized[key] = sanitizeContext(value as LogContext);
    } else {
      sanitized[key] = value;
    }
  }

  return sanitized;
}

/**
 * Format log entry for console output
 */
function formatLogEntry(entry: LogEntry): string {
  const { timestamp, level, message, context, error } = entry;

  // In development, use readable format
  if (process.env.NODE_ENV === 'development') {
    const parts = [`[${timestamp}]`, `[${level.toUpperCase()}]`, message];

    if (context && Object.keys(context).length > 0) {
      parts.push(JSON.stringify(context, null, 2));
    }

    if (error) {
      parts.push(`\nError: ${error.name}: ${error.message}`);
      if (error.stack) {
        parts.push(error.stack);
      }
    }

    return parts.join(' ');
  }

  // In production, use structured JSON
  return JSON.stringify(entry);
}

/**
 * Get the configured log level from environment variables
 */
function getConfiguredLogLevel(): LogLevelConfig {
  const configuredLevel = process.env.NEXT_PUBLIC_LOG_LEVEL as LogLevelConfig | undefined;

  if (configuredLevel && ['debug', 'info', 'warn', 'error', 'none'].includes(configuredLevel)) {
    return configuredLevel;
  }

  // Default behavior based on environment
  return process.env.NODE_ENV === 'development' ? 'debug' : 'warn';
}

/**
 * Log level hierarchy for comparison
 */
const LOG_LEVEL_PRIORITY: Record<LogLevelConfig, number> = {
  debug: 0,
  info: 1,
  warn: 2,
  error: 3,
  none: 4,
};

/**
 * Determine if log should be output based on level and environment
 */
function shouldLog(level: LogLevel): boolean {
  const configuredLevel = getConfiguredLogLevel();

  // If logging is disabled, don't log anything
  if (configuredLevel === 'none') {
    return false;
  }

  // Check if the message level meets the configured minimum level
  return LOG_LEVEL_PRIORITY[level] >= LOG_LEVEL_PRIORITY[configuredLevel];
}

/**
 * Core logging function
 */
function log(level: LogLevel, message: string, error?: Error, context?: LogContext): void {
  if (!shouldLog(level)) {
    return;
  }

  const entry: LogEntry = {
    timestamp: new Date().toISOString(),
    level,
    message,
  };

  if (context) {
    entry.context = sanitizeContext(context);
  }

  if (error) {
    entry.error = {
      name: error.name,
      message: error.message,
      stack: process.env.NODE_ENV === 'development' ? error.stack : undefined,
    };
  }

  const formatted = formatLogEntry(entry);

  switch (level) {
    case 'debug':
      console.debug(formatted);
      break;
    case 'info':
      console.info(formatted);
      break;
    case 'warn':
      console.warn(formatted);
      break;
    case 'error':
      console.error(formatted);
      break;
  }
}

/**
 * Structured Logger API
 */
export const logger = {
  /**
   * Debug level - verbose logging for development
   * Not logged in production
   */
  debug(message: string, context?: LogContext): void {
    log('debug', message, undefined, context);
  },

  /**
   * Info level - general informational messages
   * Not logged in production
   */
  info(message: string, context?: LogContext): void {
    log('info', message, undefined, context);
  },

  /**
   * Warning level - something unexpected but not critical
   * Logged in all environments
   */
  warn(message: string, context?: LogContext): void {
    log('warn', message, undefined, context);
  },

  /**
   * Error level - something went wrong
   * Logged in all environments
   */
  error(message: string, error?: Error, context?: LogContext): void {
    log('error', message, error, context);
  },
};

/**
 * Performance measurement utility
 */
export function measurePerformance<T>(operation: string, fn: () => T, context?: LogContext): T {
  const start = performance.now();

  try {
    const result = fn();
    const duration = performance.now() - start;

    logger.debug('performance_measurement', {
      ...context,
      operation,
      duration: Math.round(duration),
      unit: 'ms',
    });

    return result;
  } catch (error) {
    const duration = performance.now() - start;

    logger.error('performance_measurement_failed', error as Error, {
      ...context,
      operation,
      duration: Math.round(duration),
      unit: 'ms',
    });

    throw error;
  }
}

/**
 * Async performance measurement utility
 */
export async function measurePerformanceAsync<T>(
  operation: string,
  fn: () => Promise<T>,
  context?: LogContext
): Promise<T> {
  const start = performance.now();

  try {
    const result = await fn();
    const duration = performance.now() - start;

    logger.debug('performance_measurement', {
      ...context,
      operation,
      duration: Math.round(duration),
      unit: 'ms',
    });

    return result;
  } catch (error) {
    const duration = performance.now() - start;

    logger.error('performance_measurement_failed', error as Error, {
      ...context,
      operation,
      duration: Math.round(duration),
      unit: 'ms',
    });

    throw error;
  }
}
