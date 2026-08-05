/**
 * Which sections have data on this request.
 *
 * Drives the v2 orchestrator's idle-section folding: sections whose data is
 * absent collapse behind one per-group disclosure instead of stacking N/A
 * rows (on a conversational turn, ~2/3 of the sections are empty — pure
 * noise for analysis). The predicates mirror each section's own emptiness
 * rules — the section components stay the single authority on HOW an empty
 * state renders; this map only decides WHERE it renders.
 */

import type { DebugMetrics } from '@/types/chat';

/** Accordion value → has data on this request. */
export type SectionPresence = Record<string, boolean>;

/** Phases 1-2 — always-on analysis sections + analyzer artefacts. */
function analysisPresence(metrics: DebugMetrics): SectionPresence {
  const mechanisms = metrics.intelligent_mechanisms;
  return {
    query: true,
    intent: true,
    domain: true,
    context: true,
    routing: true,
    for_each_analysis: Boolean(metrics.for_each_analysis?.detected),
    mechanisms: mechanisms ? Object.values(mechanisms).some(m => m?.applied) : false,
  };
}

/** Phases 3-4 — planning artefacts and execution surfaces. */
function planningExecutionPresence(metrics: DebugMetrics): SectionPresence {
  return {
    token_budget: Boolean(metrics.token_budget),
    tools: Boolean(metrics.tool_selection),
    skills: Boolean(metrics.skills),
    planner: Boolean(metrics.planner_intelligence),
    semantic_validation: Boolean(metrics.semantic_validation),
    execution_waves: Boolean(metrics.execution_waves && metrics.execution_waves.total_waves > 0),
    execution: Boolean(metrics.execution_timeline),
    react_execution: Boolean(metrics.react_execution),
    hitl: Boolean(metrics.hitl),
    'google-api': (metrics.google_api_calls ?? []).length > 0,
    image_generation: (metrics.image_generation_calls ?? []).length > 0,
  };
}

/** Phases 5-6 — response context injections and background extraction. */
function injectionExtractionPresence(metrics: DebugMetrics): SectionPresence {
  const knowledge = metrics.knowledge_enrichment;
  const memoryDetection = metrics.memory_detection;
  const interests = metrics.interest_profile;
  return {
    'memory-injection': Boolean(metrics.memory_injection),
    'rag-injection': Boolean(metrics.rag_injection),
    'knowledge-enrichment': Boolean(
      knowledge && knowledge.enabled && knowledge.encyclopedia_keywords.length > 0
    ),
    'journal-injection': Boolean(metrics.journal_injection || metrics.journal_planner_injection),
    'memory-detection': Boolean(memoryDetection?.enabled && !memoryDetection.skipped_reason),
    'journal-extraction': Boolean(metrics.journal_extraction),
    'open-loop-extraction': Boolean(metrics.open_loop_extraction),
    'interest-profile': Boolean(interests?.enabled && interests.analyzed),
  };
}

/** Phase 7 — cross-cutting totals. */
function totalsPresence(metrics: DebugMetrics): SectionPresence {
  const hasLlmCalls = (metrics.llm_calls ?? []).length > 0;
  return {
    request_lifecycle: hasLlmCalls,
    llm_pipeline: hasLlmCalls,
    llm: hasLlmCalls,
    voice: Boolean(metrics.voice && metrics.voice.total_calls > 0),
    compaction: Boolean(metrics.compaction && metrics.compaction.count > 0),
  };
}

/** Compute the presence map for one request's metrics. */
export function sectionPresence(metrics: DebugMetrics): SectionPresence {
  return {
    ...analysisPresence(metrics),
    ...planningExecutionPresence(metrics),
    ...injectionExtractionPresence(metrics),
    ...totalsPresence(metrics),
  };
}
