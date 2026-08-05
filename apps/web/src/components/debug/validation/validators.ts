/**
 * Validation Functions for Debug Metrics
 *
 * v3.1 LLM-based: the LLM directly produces confidence scores.
 * v3.4: Zod runs as a DETECTOR — `validateSectionSchemas` feeds the anomaly
 * channel (a drifted payload surfaces as a warning; no section ever
 * disappears or crashes because of it).
 */

import { logger } from '@/lib/logger';
import {
  DomainSelectionMetricsSchema,
  SECTION_SCHEMAS,
  ToolSelectionMetricsSchema,
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

/** One schema mismatch found on a present section. */
export interface SectionSchemaMismatch {
  /** Accordion value of the drifted section. */
  section: string;
  /** Human-readable summary of the first mismatch. */
  label: string;
}

/**
 * Map from payload keys to accordion values where they differ.
 *
 * `SECTION_SCHEMAS` is keyed by DebugMetrics payload key; the anomaly
 * channel targets accordion section values.
 */
const PAYLOAD_KEY_TO_SECTION: Record<string, string> = {
  intent_detection: 'intent',
  domain_selection: 'domain',
  routing_decision: 'routing',
  context_resolution: 'context',
  query_info: 'query',
  tool_selection: 'tools',
  planner_intelligence: 'planner',
  execution_timeline: 'execution',
  intelligent_mechanisms: 'mechanisms',
  llm_calls: 'llm',
  llm_summary: 'llm',
  image_generation_calls: 'image_generation',
  image_generation_summary: 'image_generation',
};

/**
 * Run every PRESENT section through its schema, fail-soft.
 *
 * Args mirror the panel's per-entry pass: absent sections are skipped
 * (absence is presence's business, not validation's).
 *
 * @param metrics - One request's debug metrics.
 * @returns One mismatch per drifted section (empty when all conform).
 */
export function validateSectionSchemas(metrics: DebugMetrics): SectionSchemaMismatch[] {
  const mismatches: SectionSchemaMismatch[] = [];
  // Indexed read over the registry keys: DebugMetrics has no index
  // signature, so the registry lookup goes through unknown on purpose.
  const payload: Record<string, unknown> = { ...metrics };
  for (const [key, schema] of Object.entries(SECTION_SCHEMAS)) {
    const value = payload[key];
    if (value === undefined || value === null) continue;
    const result = schema.safeParse(value);
    if (!result.success) {
      const first = result.error.issues[0];
      const path = first?.path.join('.') || key;
      mismatches.push({
        section: PAYLOAD_KEY_TO_SECTION[key] ?? key,
        label: `Payload mismatch in ${key} (${path}: ${first?.message ?? 'invalid'})`,
      });
      logger.warn('debug_section_schema_mismatch', {
        section: key,
        issues: result.error.issues.slice(0, 3),
      });
    }
  }
  return mismatches;
}

/**
 * Validate domain scores
 *
 * v3.1 LLM-based: Simplified validation.
 * The LLM directly produces confidence scores (no more CAL/RAW).
 *
 * @param domainSelection - Domain selection metrics
 * @returns Result with validated scores
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
 * @returns Result with validated scores or SECTION_ABSENT when the query
 *     was not routed to the planner.
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
