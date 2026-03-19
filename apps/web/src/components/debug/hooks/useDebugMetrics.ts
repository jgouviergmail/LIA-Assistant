/**
 * useDebugMetrics Hook
 *
 * Returns the current debug metrics with validation.
 *
 * SIMPLIFIED ARCHITECTURE (v3.2):
 * - Metrics are stored directly in state (not indexed by messageId)
 * - Cleared on each new request (SEND_MESSAGE)
 * - Set when debug_metrics chunk arrives
 * - No more ID synchronization issues
 *
 * This eliminates the previous mismatch problems where:
 * - Frontend generated assistantMessageId
 * - Backend could use different messageId (HITL flow)
 * - Hook couldn't find metrics due to ID mismatch
 */

import { DebugMetrics } from '@/types/chat';
import { logger } from '@/lib/logger';

export interface UseDebugMetricsResult {
  /** Validated debug metrics (or null if unavailable) */
  metrics: DebugMetrics | null;
  /** true if metrics found and valid */
  isValid: boolean;
  /** List of validation errors */
  errors: string[];
}

// Cached result for null metrics (avoids recreation)
const NULL_METRICS_RESULT: UseDebugMetricsResult = {
  metrics: null,
  isValid: false,
  errors: ['No debug metrics available (request in progress or DEBUG=false)'],
};

// Cached result for valid metrics (errors array reused)
const EMPTY_ERRORS: string[] = [];

/**
 * Validates debug metrics and returns validation result
 * Pure function - React Compiler can optimize automatically
 */
function validateDebugMetrics(currentDebugMetrics: DebugMetrics | null): UseDebugMetricsResult {
  // No metrics available
  if (!currentDebugMetrics) {
    return NULL_METRICS_RESULT;
  }

  // Validate required sections
  const validationErrors: string[] = [];

  if (!currentDebugMetrics.intent_detection) {
    validationErrors.push('Missing intent_detection');
  }
  if (!currentDebugMetrics.domain_selection) {
    validationErrors.push('Missing domain_selection');
  }
  if (!currentDebugMetrics.routing_decision) {
    validationErrors.push('Missing routing_decision');
  }
  if (!currentDebugMetrics.context_resolution) {
    validationErrors.push('Missing context_resolution');
  }
  if (!currentDebugMetrics.query_info) {
    validationErrors.push('Missing query_info');
  }

  if (validationErrors.length > 0) {
    logger.error('debug_metrics_validation_failed', undefined, {
      errors: validationErrors,
    });

    return {
      metrics: null,
      isValid: false,
      errors: validationErrors,
    };
  }

  // Metrics are valid
  return {
    metrics: currentDebugMetrics,
    isValid: true,
    errors: EMPTY_ERRORS,
  };
}

/**
 * Hook to get current debug metrics with validation
 *
 * @param currentDebugMetrics - Current debug metrics from chat state (or null)
 * @returns Result with metrics, validation status, and errors
 *
 * @example
 * \`\`\`tsx
 * const { metrics, isValid, errors } = useDebugMetrics(currentDebugMetrics);
 *
 * if (!isValid) {
 *   console.warn('Debug metrics issues:', errors);
 * }
 *
 * return <DebugPanel metrics={metrics} />;
 * \`\`\`
 */
export function useDebugMetrics(currentDebugMetrics: DebugMetrics | null): UseDebugMetricsResult {
  // React Compiler will automatically memoize this pure function call
  return validateDebugMetrics(currentDebugMetrics);
}

/**
 * Simplified hook that returns metrics directly or null
 *
 * @param currentDebugMetrics - Current debug metrics from chat state
 * @returns Debug metrics or null
 *
 * @example
 * \`\`\`tsx
 * const metrics = useSimpleDebugMetrics(currentDebugMetrics);
 * if (!metrics) return null;
 * return <DebugPanel metrics={metrics} />;
 * \`\`\`
 */
export function useSimpleDebugMetrics(
  currentDebugMetrics: DebugMetrics | null
): DebugMetrics | null {
  const { metrics } = useDebugMetrics(currentDebugMetrics);
  return metrics;
}
