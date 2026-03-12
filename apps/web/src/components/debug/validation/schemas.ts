/**
 * Zod Validation Schemas for Debug Metrics
 *
 * Validates the structure of debug metrics received from the backend.
 * Detects anomalies, RAW vs CAL scores, and missing data.
 */

import { z } from 'zod';

/**
 * Schema for a threshold comparison
 */
const ThresholdCheckSchema = z.object({
  value: z.number(),
  actual: z.number(),
  passed: z.boolean(),
});

/**
 * Schema for threshold information (without comparison)
 */
const ThresholdInfoSchema = z.object({
  value: z.union([z.number(), z.string()]),
  info: z.string().optional(),
});

/**
 * Schema for intent detection metrics
 */
export const IntentDetectionMetricsSchema = z.object({
  detected_intent: z.string(),
  confidence: z.number().min(0).max(1),
  user_goal: z.string(),
  goal_reasoning: z.string().optional(),
  thresholds: z.object({
    high_threshold: ThresholdCheckSchema.optional(),
    fallback_threshold: ThresholdCheckSchema.optional(),
  }),
});

/**
 * Schema for domain selection metrics
 *
 * v3.1 LLM-based: The LLM selects domains with a single confidence score.
 * No more CAL/RAW distinction (legacy embeddings + softmax concept).
 */
export const DomainSelectionMetricsSchema = z.object({
  selected_domains: z.array(z.string()),
  primary_domain: z.string(),
  top_score: z.number().min(0).max(1),

  // LLM confidence scores (all domains have same confidence)
  all_scores: z.record(z.string(), z.number()).optional(),

  thresholds: z.object({
    primary_min: ThresholdCheckSchema.optional(),
    max_domains: ThresholdInfoSchema.optional(),
  }),
});

/**
 * Schema for routing decision metrics
 */
export const RoutingDecisionMetricsSchema = z.object({
  route_to: z.enum(['chat', 'planner']),
  confidence: z.number().min(0).max(1),
  bypass_llm: z.boolean(),
  reasoning_trace: z.array(z.string()).default([]),
  thresholds: z.object({
    chat_semantic_threshold: ThresholdCheckSchema.optional(),
    high_semantic_threshold: ThresholdCheckSchema.optional(),
    min_confidence: ThresholdCheckSchema.optional(),
    chat_override_threshold: ThresholdInfoSchema.optional(),
  }),
});

/**
 * Schema for context resolution metrics
 */
export const ContextResolutionMetricsSchema = z.object({
  turn_type: z.string(),
  is_reference: z.boolean(),
  source_turn_id: z.number().nullable(),
  source_domain: z.string().nullable(),
  resolved_references: z.record(z.string(), z.string()).nullable(),
  thresholds: z.object({
    confidence_threshold: ThresholdInfoSchema.optional(),
    active_window_turns: ThresholdInfoSchema.optional(),
  }),
});

/**
 * Schema for query information
 */
export const QueryInfoMetricsSchema = z.object({
  original_query: z.string(),
  english_query: z.string(),
  english_enriched_query: z.string().nullable(),
  user_language: z.string(),
  implicit_intents: z.array(z.string()),
  anticipated_needs: z.array(z.string()),
  fallback_strategies: z.array(z.string()),
});

/**
 * Schema for a tool match
 */
const ToolMatchSchema = z.object({
  tool_name: z.string(),
  score: z.number().min(0).max(1),
  confidence: z.enum(['high', 'medium', 'low']),
});

/**
 * Schema for tool selection metrics
 *
 * v3.1 LLM-based: The planner selects tools directly.
 * Can be completely absent if no tool selection was performed.
 */
export const ToolSelectionMetricsSchema = z.object({
  selected_tools: z.array(ToolMatchSchema),
  top_score: z.number().min(0).max(1),
  has_uncertainty: z.boolean(),
  all_scores: z.record(z.string(), z.number()).optional(),

  thresholds: z.object({
    primary_min: ThresholdCheckSchema.optional(),
    max_tools: ThresholdInfoSchema.optional(),
  }),
}).optional(); // The entire section can be absent!

/**
 * Schema for token budget
 */
const TokenBudgetSchema = z.object({
  current_tokens: z.number().min(0),
  thresholds: z.object({
    safe: z.number(),
    warning: z.number(),
    critical: z.number(),
    max: z.number(),
  }),
  zone: z.enum(['safe', 'warning', 'critical', 'emergency']),
  strategy: z.string().optional(),
  fallback_active: z.boolean().optional(),
}).optional();

/**
 * Schema for an execution step
 */
const ExecutionStepSchema = z.object({
  step_id: z.string(),
  tool_name: z.string(),
  domain: z.string(),
  status: z.enum(['pending', 'running', 'completed', 'error']),
  success: z.boolean().nullable().optional(),
  duration_ms: z.number().nullable().optional(),

  // NEW fields (Phase 6)
  start_time: z.string().optional(),
  end_time: z.string().optional(),
  error_message: z.string().optional(),
  latency_breakdown: z.object({
    api_call_ms: z.number(),
    processing_ms: z.number(),
    serialization_ms: z.number(),
  }).optional(),
  result_metrics: z.object({
    items_count: z.number(),
    items_filtered: z.number(),
    result_size_kb: z.number(),
  }).optional(),
});

/**
 * Schema for execution timeline
 */
const ExecutionTimelineSchema = z.object({
  steps: z.array(ExecutionStepSchema),
  total_steps: z.number(),
  completed_steps: z.number(),
}).optional();

/**
 * Schema for planner intelligence
 */
const PlannerIntelligenceSchema = z.object({
  strategy: z.enum(['template_bypass', 'filtered_catalogue', 'generative', 'panic_mode']),
  tokens: z.object({
    used: z.number(),
    saved: z.number(),
    full_catalogue_estimate: z.number(),
    reduction_percentage: z.number(),
  }),
  plan: z.object({
    steps_count: z.number().optional(),
    tools_used: z.array(z.string()).optional(),
    estimated_cost_usd: z.number().nullable().optional(),
  }),
  flags: z.object({
    used_template: z.boolean(),
    used_panic_mode: z.boolean(),
    used_generative: z.boolean(),
  }),
  success: z.boolean(),
  error: z.string().nullable().optional(),
}).optional();

/**
 * Schema for an LLM call
 */
const LLMCallSchema = z.object({
  node_name: z.string(),
  model_name: z.string(),
  tokens_in: z.number().min(0),
  tokens_out: z.number().min(0),
  tokens_cache: z.number().min(0),
  cost_eur: z.number().min(0),
});

/**
 * Schema for LLM calls summary
 */
const LLMSummarySchema = z.object({
  total_calls: z.number().min(0),
  total_tokens_in: z.number().min(0),
  total_tokens_out: z.number().min(0),
  total_tokens_cache: z.number().min(0),
  total_cost_eur: z.number().min(0),
}).optional();

/**
 * Schema for Memory Resolution
 */
const MemoryResolutionSchema = z.object({
  applied: z.boolean(),
  original_query: z.string(),
  enriched_query: z.string(),
  mappings: z.record(z.string(), z.string()),
  num_references: z.number().min(0),
}).optional();

/**
 * Schema for Semantic Pivot
 */
const SemanticPivotSchema = z.object({
  applied: z.boolean(),
  source_language: z.string(),
  original_query: z.string(),
  translated_query: z.string(),
}).optional();

/**
 * Schema for Semantic Expansion
 */
const SemanticExpansionSchema = z.object({
  applied: z.boolean(),
  original_domains: z.array(z.string()),
  expanded_domains: z.array(z.string()),
  added_domains: z.array(z.string()),
  reasons: z.array(z.string()),
  has_person_reference: z.boolean(),
}).optional();

/**
 * Schema for Chat Override
 */
const ChatOverrideSchema = z.object({
  applied: z.boolean(),
  original_domains: z.array(z.string()),
  original_top_score: z.number(),
  intent_confidence: z.number().min(0).max(1),
  override_threshold: z.number().min(0).max(1),
  reason: z.string(),
}).optional();

/**
 * Schema for Intelligent Mechanisms
 */
const IntelligentMechanismsSchema = z.object({
  memory_resolution: MemoryResolutionSchema,
  semantic_pivot: SemanticPivotSchema,
  semantic_expansion: SemanticExpansionSchema,
  chat_override: ChatOverrideSchema,
}).optional();

/**
 * Schema pour FOR_EACH Analysis (v3.1)
 * Bulk operation detection
 */
export const ForEachAnalysisSchema = z.object({
  detected: z.boolean(),
  collection_key: z.string().nullable(),
  cardinality_magnitude: z.number().nullable(),
  cardinality_mode: z.enum(['single', 'multiple', 'all', 'each']),
  constraint_hints: z.record(z.string(), z.boolean()).default({}),
}).optional();

/**
 * Schema pour Execution Waves (v3.1)
 * Parallel execution visualization
 */
const ExecutionWaveSchema = z.object({
  wave_id: z.number(),
  steps: z.array(z.string()),
  size: z.number(),
});

export const ExecutionWavesSchema = z.object({
  total_waves: z.number(),
  max_parallelism: z.number(),
  critical_path_length: z.number(),
  waves: z.array(ExecutionWaveSchema),
  average_parallelism: z.number(),
}).optional();

/**
 * Schema pour Request Lifecycle (v3.1)
 * Pipeline node progression
 */
const LifecycleNodeSchema = z.object({
  name: z.string(),
  status: z.literal('completed'),
  tokens_in: z.number(),
  tokens_out: z.number(),
  tokens_cache: z.number(),
  cost_eur: z.number(),
  calls_count: z.number(),
});

export const RequestLifecycleSchema = z.object({
  nodes: z.array(LifecycleNodeSchema),
  total_nodes: z.number(),
}).optional();

/**
 * Main schema for all debug metrics
 */
export const DebugMetricsSchema = z.object({
  // Required sections (always present)
  intent_detection: IntentDetectionMetricsSchema,
  domain_selection: DomainSelectionMetricsSchema,
  routing_decision: RoutingDecisionMetricsSchema,
  context_resolution: ContextResolutionMetricsSchema,
  query_info: QueryInfoMetricsSchema,

  // Sections optionnelles (conditionnelles)
  tool_selection: ToolSelectionMetricsSchema,
  token_budget: TokenBudgetSchema,
  planner_intelligence: PlannerIntelligenceSchema,
  execution_timeline: ExecutionTimelineSchema,
  llm_calls: z.array(LLMCallSchema).optional(),
  llm_summary: LLMSummarySchema,
  intelligent_mechanisms: IntelligentMechanismsSchema,
  // v3.1 Debug Panel Enrichments
  for_each_analysis: ForEachAnalysisSchema,
  execution_waves: ExecutionWavesSchema,
  request_lifecycle: RequestLifecycleSchema,
});

/**
 * Inferred type from the schema (for TypeScript)
 */
export type ValidatedDebugMetrics = z.infer<typeof DebugMetricsSchema>;

/**
 * Helper to check score type
 *
 * v3.1 LLM-based: No more CAL/RAW distinction.
 * The LLM directly produces confidence scores.
 * This function is kept for backward compatibility.
 *
 * @param scores - Scores dictionary
 * @returns Always 'calibrated' in v3.1
 * @deprecated In v3.1, scores are always of LLM confidence type
 */
export function detectScoreType(
  scores: Record<string, number>
): 'calibrated' | 'raw' | 'unknown' {
  const values = Object.values(scores);
  if (values.length === 0) return 'unknown';

  // v3.1: LLM confidence scores are always "calibrated" (no softmax/embeddings)
  return 'calibrated';
}
