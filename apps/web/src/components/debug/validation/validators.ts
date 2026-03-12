/**
 * Validation Functions for Debug Metrics
 *
 * v3.1 LLM-based: Simplified validation.
 * No more CAL/RAW distinction - the LLM directly produces confidence scores.
 */

import { logger } from '@/lib/logger';
import {
  DebugMetricsSchema,
  DomainSelectionMetricsSchema,
  ToolSelectionMetricsSchema,
  type ValidatedDebugMetrics,
} from './schemas';
import type { DebugMetrics } from '@/types/chat';

/**
 * Validation result
 */
export interface ValidationResult<T = unknown> {
  /** true if validation succeeded */
  success: boolean;
  /** Validated data (if success=true) */
  data?: T;
  /** List of errors (if success=false) */
  errors?: string[];
  /** Detected type (for scores) */
  type?: 'calibrated' | 'raw' | 'unknown';
  /** Optional warning message */
  warning?: string;
}

/**
 * Validate complete debug metrics
 *
 * Uses Zod to validate the structure and detect anomalies.
 *
 * @param rawMetrics - Raw metrics received from the backend
 * @returns Validation result with validated data or errors
 *
 * @example
 * ```typescript
 * const result = validateDebugMetrics(rawData);
 * if (!result.success) {
 *   console.error('Validation failed:', result.errors);
 *   return;
 * }
 * const metrics = result.data; // Type-safe validated metrics
 * ```
 */
export function validateDebugMetrics(
  rawMetrics: unknown
): ValidationResult<ValidatedDebugMetrics> {
  // Zod validation
  const result = DebugMetricsSchema.safeParse(rawMetrics);

  if (!result.success) {
    const errors = result.error.issues.map(
      e => `${e.path.join('.')}: ${e.message}`
    );

    logger.error('debug_metrics_validation_failed', undefined, {
      errors: result.error.issues,
      rawData: rawMetrics,
    });

    return {
      success: false,
      errors,
    };
  }

  // Validation succeeded
  return {
    success: true,
    data: result.data,
  };
}

/**
 * Validate domain scores
 *
 * v3.1 LLM-based: Simplified validation.
 * The LLM directly produces confidence scores (no more CAL/RAW).
 *
 * @param domainSelection - Domain selection metrics
 * @returns Result with validated scores
 *
 * @example
 * ```typescript
 * const result = validateDomainScores(metrics.domain_selection);
 * if (!result.success) {
 *   return <ErrorDisplay message={result.errors[0]} />;
 * }
 * return <ScoresList scores={result.data} />;
 * ```
 */
export function validateDomainScores(
  domainSelection: DebugMetrics['domain_selection']
): ValidationResult<Record<string, number>> {
  // Structure validation with Zod
  const schemaResult = DomainSelectionMetricsSchema.safeParse(domainSelection);

  if (!schemaResult.success) {
    logger.error('domain_selection_schema_validation_failed', undefined, {
      errors: schemaResult.error.issues,
    });

    return {
      success: false,
      errors: ['Invalid domain_selection structure'],
    };
  }

  const data = schemaResult.data!;

  // Check for score presence
  if (data.all_scores && Object.keys(data.all_scores).length > 0) {
    return {
      success: true,
      data: data.all_scores,
      type: 'calibrated', // v3.1: LLM confidence scores
    };
  }

  // No scores available - normal case for "general" domain or simple queries
  // Use warn instead of error since this is not an application error
  logger.warn('domain_scores_missing', {
    primary_domain: data.primary_domain,
    selected_domains: data.selected_domains,
    top_score: data.top_score,
  });

  return {
    success: false,
    errors: ['No domain scores available.'],
  };
}

/**
 * Validate tool scores
 *
 * v3.1 LLM-based: Simplified validation.
 * The planner selects tools directly (no more CAL/RAW).
 *
 * @param toolSelection - Tool selection metrics (can be undefined)
 * @returns Result with validated scores or null if section absent
 *
 * @example
 * ```typescript
 * const result = validateToolScores(metrics.tool_selection);
 *
 * if (result.success === false && result.errors?.[0] === 'SECTION_ABSENT') {
 *   return <InfoMessage>Tool selection not performed</InfoMessage>;
 * }
 *
 * if (!result.success) {
 *   return <ErrorDisplay message={result.errors[0]} />;
 * }
 *
 * return <ScoresList scores={result.data} />;
 * ```
 */
export function validateToolScores(
  toolSelection: DebugMetrics['tool_selection']
): ValidationResult<Record<string, number>> {
  // Section completely absent (query was not routed to planner)
  if (!toolSelection) {
    return {
      success: false,
      errors: ['SECTION_ABSENT'],
    };
  }

  // Structure validation with Zod
  const schemaResult = ToolSelectionMetricsSchema.safeParse(toolSelection);

  if (!schemaResult.success) {
    logger.error('tool_selection_schema_validation_failed', undefined, {
      errors: schemaResult.error.issues,
    });

    return {
      success: false,
      errors: ['Invalid tool_selection structure'],
    };
  }

  const data = schemaResult.data!;

  // Check for score presence
  if (data.all_scores && Object.keys(data.all_scores).length > 0) {
    return {
      success: true,
      data: data.all_scores,
      type: 'calibrated', // v3.1: LLM/planner confidence scores
    };
  }

  // No scores available
  logger.error('tool_scores_missing', undefined, {
    selected_tools: data.selected_tools,
    top_score: data.top_score,
  });

  return {
    success: false,
    errors: ['No tool scores available.'],
  };
}

/**
 * Validate intent detection metrics
 *
 * @param intentDetection - Intent metrics
 * @returns Validation result
 */
export function validateIntentDetection(
  intentDetection: DebugMetrics['intent_detection']
): ValidationResult<DebugMetrics['intent_detection']> {
  if (!intentDetection) {
    return {
      success: false,
      errors: ['Intent detection metrics missing'],
    };
  }

  // Basic checks
  if (
    intentDetection.confidence < 0 ||
    intentDetection.confidence > 1
  ) {
    logger.warn('intent_detection_invalid_confidence', {
      confidence: intentDetection.confidence,
    });

    return {
      success: false,
      errors: ['Confidence must be between 0 and 1'],
    };
  }

  return {
    success: true,
    data: intentDetection,
  };
}

/**
 * Validate routing decision metrics
 *
 * @param routingDecision - Routing metrics
 * @returns Validation result
 */
export function validateRoutingDecision(
  routingDecision: DebugMetrics['routing_decision']
): ValidationResult<DebugMetrics['routing_decision']> {
  if (!routingDecision) {
    return {
      success: false,
      errors: ['Routing decision metrics missing'],
    };
  }

  // Check valid route_to
  if (!['chat', 'planner'].includes(routingDecision.route_to)) {
    logger.error('routing_decision_invalid_route', undefined, {
      route_to: routingDecision.route_to,
    });

    return {
      success: false,
      errors: [`Invalid route_to value: ${routingDecision.route_to}`],
    };
  }

  // Check confidence
  if (
    routingDecision.confidence < 0 ||
    routingDecision.confidence > 1
  ) {
    logger.warn('routing_decision_invalid_confidence', {
      confidence: routingDecision.confidence,
    });

    return {
      success: false,
      errors: ['Confidence must be between 0 and 1'],
    };
  }

  return {
    success: true,
    data: routingDecision,
  };
}

/**
 * Validate token budget
 *
 * Checks that thresholds are consistent (safe < warning < critical < max)
 *
 * @param tokenBudget - Token budget metrics (can be undefined)
 * @returns Validation result
 */
export function validateTokenBudget(
  tokenBudget: DebugMetrics['token_budget']
): ValidationResult<NonNullable<DebugMetrics['token_budget']>> {
  if (!tokenBudget) {
    return {
      success: false,
      errors: ['SECTION_ABSENT'],
    };
  }

  const { current_tokens, thresholds } = tokenBudget;

  // Check threshold consistency
  const { safe, warning, critical, max } = thresholds;

  if (!(safe < warning && warning < critical && critical <= max)) {
    logger.error('token_budget_invalid_thresholds', undefined, {
      thresholds,
      message: 'Thresholds must be: safe < warning < critical <= max',
    });

    return {
      success: false,
      errors: ['Invalid token budget thresholds (not monotonic)'],
    };
  }

  // Check that current_tokens is valid
  if (current_tokens < 0) {
    logger.warn('token_budget_negative_current', {
      current_tokens,
    });

    return {
      success: false,
      errors: ['Current tokens cannot be negative'],
    };
  }

  return {
    success: true,
    data: tokenBudget,
  };
}

/**
 * Validate planner intelligence
 *
 * @param plannerIntelligence - Planner metrics (can be undefined)
 * @returns Validation result
 */
export function validatePlannerIntelligence(
  plannerIntelligence: DebugMetrics['planner_intelligence']
): ValidationResult<NonNullable<DebugMetrics['planner_intelligence']>> {
  if (!plannerIntelligence) {
    return {
      success: false,
      errors: ['SECTION_ABSENT'],
    };
  }

  // Check token consistency
  const { tokens } = plannerIntelligence;

  if (tokens.used < 0 || tokens.saved < 0 || tokens.full_catalogue_estimate < 0) {
    logger.warn('planner_intelligence_invalid_tokens', {
      tokens,
    });

    return {
      success: false,
      errors: ['Token counts cannot be negative'],
    };
  }

  // Check reduction_percentage consistency
  if (
    tokens.reduction_percentage < 0 ||
    tokens.reduction_percentage > 100
  ) {
    logger.warn('planner_intelligence_invalid_reduction', {
      reduction_percentage: tokens.reduction_percentage,
    });

    return {
      success: false,
      errors: ['Reduction percentage must be between 0 and 100'],
    };
  }

  return {
    success: true,
    data: plannerIntelligence,
  };
}

/**
 * Sanitize and validate a numeric value
 *
 * Handles NaN, Infinity, negative values based on context
 *
 * @param value - Value to validate
 * @param options - Validation options
 * @returns Sanitized value or null if invalid
 */
export function sanitizeNumericValue(
  value: unknown,
  options: {
    min?: number;
    max?: number;
    allowNegative?: boolean;
    defaultValue?: number;
  } = {}
): number | null {
  const {
    min = -Infinity,
    max = Infinity,
    allowNegative = true,
    defaultValue = null,
  } = options;

  if (typeof value !== 'number') {
    return defaultValue;
  }

  if (!isFinite(value)) {
    logger.warn('sanitize_numeric_non_finite', { value });
    return defaultValue;
  }

  if (!allowNegative && value < 0) {
    logger.warn('sanitize_numeric_negative', { value });
    return defaultValue;
  }

  if (value < min || value > max) {
    logger.warn('sanitize_numeric_out_of_range', { value, min, max });
    return defaultValue;
  }

  return value;
}

/**
 * Validate that a score is within the [0, 1] range
 *
 * @param score - Score to validate
 * @param context - Context for logging (e.g., "domain_score", "tool_score")
 * @returns true if valid
 */
export function validateScoreRange(
  score: number,
  context: string = 'score'
): boolean {
  if (!isFinite(score)) {
    logger.warn('validate_score_non_finite', { score, context });
    return false;
  }

  if (score < 0 || score > 1) {
    logger.warn('validate_score_out_of_range', { score, context });
    return false;
  }

  return true;
}
