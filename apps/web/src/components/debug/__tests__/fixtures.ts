/**
 * Typed test fixtures for the debug panel.
 *
 * One builder, precise override types (`Partial<DebugMetrics>`), no casts —
 * test data obeys the production contract (thresholds are REQUIRED on the
 * analysis sections; a `{}` fixture was a contract violation tsc caught).
 */

import type { DebugMetrics, ThresholdCheck, ThresholdInfo } from '@/types/chat';

/** Passing threshold-check literal. */
export function passedCheck(value: number, actual: number): ThresholdCheck {
  return { value, actual, passed: actual >= value };
}

/** Informational threshold literal. */
export function infoCheck(value: number | string, info = ''): ThresholdInfo {
  return { value, info };
}

/**
 * Fully-typed minimal metrics of a conversational (chat-routed) turn.
 *
 * @param overrides - Section-level overrides merged on top.
 * @returns A contract-conforming DebugMetrics value.
 */
export function baseDebugMetrics(overrides: Partial<DebugMetrics> = {}): DebugMetrics {
  return {
    intent_detection: {
      detected_intent: 'conversation',
      confidence: 0.9,
      user_goal: 'chat',
      goal_reasoning: 'simple greeting',
      thresholds: {
        high_threshold: passedCheck(0.7, 0.9),
        fallback_threshold: passedCheck(0.5, 0.9),
      },
    },
    domain_selection: {
      selected_domains: [],
      primary_domain: 'none',
      top_score: 0,
      all_scores: {},
      thresholds: {
        primary_min: passedCheck(0.15, 0),
        max_domains: infoCheck(3, 'Maximum domains to select'),
      },
    },
    routing_decision: {
      route_to: 'chat',
      confidence: 0.9,
      bypass_llm: false,
      reasoning_trace: [],
      thresholds: {
        chat_semantic_threshold: passedCheck(0.4, 0.9),
        high_semantic_threshold: passedCheck(0.7, 0.9),
        min_confidence: passedCheck(0.5, 0.9),
        chat_override_threshold: infoCheck(0.75, 'override'),
      },
    },
    context_resolution: {
      turn_type: 'initial',
      is_reference: false,
      source_turn_id: null,
      source_domain: null,
      resolved_references: null,
      thresholds: {
        confidence_threshold: infoCheck(0.6, 'min confidence'),
        active_window_turns: infoCheck(6, 'window'),
      },
    },
    query_info: {
      original_query: 'salut lia',
      english_query: 'hi lia',
      english_enriched_query: null,
      user_language: 'fr',
      implicit_intents: [],
      anticipated_needs: [],
      fallback_strategies: [],
    },
    ...overrides,
  };
}
