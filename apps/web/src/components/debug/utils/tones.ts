/**
 * Tone foundation for the debug panel — the single colour authority.
 *
 * Two kinds of colour live here, deliberately separated:
 *
 * 1. **Semantic tones** (`DebugTone`): pass/fail, zones, statuses, tiers.
 *    They resolve to design-system tokens (`success`, `warning`,
 *    `destructive`, `primary`) which follow the five themes and light/dark
 *    by construction, and to `Badge` variants so chips inherit the
 *    app-wide contrast guard. Severity follows the ADR-205 doctrine:
 *    density, not hue alone, carries the top level (`alert` is the only
 *    solid fill).
 *
 * 2. **Identity hues** (node families): router vs planner vs react are not
 *    statuses — they need distinct, stable identities. Those keep raw
 *    Tailwind hues but ALWAYS as a bi-theme pair (light text + `dark:`
 *    counterpart), replacing the old dark-only `NODE_COLORS`.
 *
 * Score tiers previously lived as four divergent inline copies (0.8/0.6 in
 * memory, 0.7/0.5 in RAG and journals, 0.8/0.5 in interests); they are now
 * one documented table keyed by score space.
 */

import type { BadgeTone } from '@/lib/status-tone';
import { lifecycleTone } from '@/lib/status-tone';

// ============================================================================
// Semantic tones
// ============================================================================

export type DebugTone = 'success' | 'info' | 'warning' | 'destructive' | 'alert' | 'neutral';

/** Inline text colour per tone — tokens only, theme-aware by construction. */
export const TONE_TEXT: Record<DebugTone, string> = {
  success: 'text-success',
  info: 'text-primary',
  warning: 'text-warning',
  destructive: 'text-destructive',
  alert: 'text-destructive',
  neutral: 'text-muted-foreground',
};

/** Solid bar/dot colour per tone — tokens only. */
export const TONE_BAR: Record<DebugTone, string> = {
  success: 'bg-success',
  info: 'bg-primary',
  warning: 'bg-warning',
  destructive: 'bg-destructive',
  alert: 'bg-destructive',
  neutral: 'bg-muted-foreground',
};

/**
 * Map a debug tone onto the `Badge` variant that renders it.
 *
 * Chips therefore inherit the design-system contrast guard (five themes ×
 * light/dark) instead of re-painting their own grounds.
 */
export function badgeVariantFor(tone: DebugTone): BadgeTone {
  return tone === 'neutral' ? 'secondary' : tone;
}

// ============================================================================
// Semantic mappers
// ============================================================================

const CONFIDENCE_TONE: Record<'high' | 'medium' | 'low', DebugTone> = {
  high: 'success',
  medium: 'warning',
  low: 'destructive',
};

/** Tone for a high/medium/low confidence level. */
export function confidenceTone(level: 'high' | 'medium' | 'low'): DebugTone {
  return CONFIDENCE_TONE[level];
}

const ZONE_TONE: Record<string, DebugTone> = {
  safe: 'success',
  warning: 'warning',
  critical: 'destructive',
  // The only solid fill: past `critical`, a pale tint 23° away would read as
  // the same level (ADR-205 measurement) — density carries the hierarchy.
  emergency: 'alert',
};

/** Tone for a token-budget zone. Unknown zones stay neutral. */
export function zoneTone(zone: string): DebugTone {
  return ZONE_TONE[zone] ?? 'neutral';
}

const STRATEGY_TONE: Record<string, DebugTone> = {
  // Graded by degradation of the planning path, not by identity: bypass is
  // the best economy, panic is the emergency fallback.
  template_bypass: 'success',
  filtered_catalogue: 'info',
  generative: 'info',
  panic_mode: 'destructive',
};

/** Tone for a planner strategy. Unknown strategies stay neutral. */
export function strategyTone(strategy: string): DebugTone {
  return STRATEGY_TONE[strategy] ?? 'neutral';
}

const FALLBACK_LEVEL_TONE: Record<string, DebugTone> = {
  // Same severity scale as the zones the backend derives from these levels
  // (FULL→safe, FILTERED/REDUCED→warning, PRIMARY→critical, SIMPLE→emergency).
  full_catalogue: 'success',
  filtered_catalogue: 'warning',
  reduced_descriptions: 'warning',
  primary_domain_only: 'destructive',
  simple_search: 'alert',
};

/** Tone for a catalogue fallback level. Unknown levels stay neutral. */
export function fallbackLevelTone(level: string): DebugTone {
  return FALLBACK_LEVEL_TONE[level] ?? 'neutral';
}

const BADGE_TONE_TO_DEBUG: Record<BadgeTone, DebugTone> = {
  default: 'info',
  alert: 'alert',
  secondary: 'neutral',
  success: 'success',
  destructive: 'destructive',
  warning: 'warning',
  info: 'info',
  outline: 'neutral',
};

/**
 * Tone for an execution step status, via the app-wide lifecycle vocabulary
 * (`lib/status-tone.ts`) so `completed`/`running`/`error` mean the same thing
 * in the debug panel as everywhere else. Unknown statuses stay neutral.
 */
export function executionStatusTone(status: string): DebugTone {
  return BADGE_TONE_TO_DEBUG[lifecycleTone(status)];
}

// ============================================================================
// Score tiers — one table, three documented score spaces
// ============================================================================

export type ScoreSpace = 'similarity' | 'relevance' | 'confidence';
export type ScoreTier = 'high' | 'medium' | 'low';

/**
 * Tier thresholds per score space.
 *
 * - `similarity`: memory-injection cosine similarity (dense space, scores
 *   cluster high — 0.80/0.60).
 * - `relevance`: RAG chunk and journal retrieval relevance (0.70/0.50).
 * - `confidence`: LLM-reported extraction confidence (0.80/0.50).
 */
export const SCORE_SPACES: Record<ScoreSpace, { high: number; medium: number }> = {
  similarity: { high: 0.8, medium: 0.6 },
  relevance: { high: 0.7, medium: 0.5 },
  confidence: { high: 0.8, medium: 0.5 },
};

/** Classify a 0..1 score into its tier for the given score space. */
export function scoreTier(score: number, space: ScoreSpace): ScoreTier {
  const { high, medium } = SCORE_SPACES[space];
  if (score >= high) return 'high';
  if (score >= medium) return 'medium';
  return 'low';
}

const TIER_TONE: Record<ScoreTier, DebugTone> = {
  high: 'success',
  medium: 'warning',
  low: 'destructive',
};

/** Tone for a score tier (bars, dots, legends). */
export function tierTone(tier: ScoreTier): DebugTone {
  return TIER_TONE[tier];
}

// ============================================================================
// Node identity families
// ============================================================================

export type NodeFamily =
  | 'analysis'
  | 'planning'
  | 'hitl'
  | 'execution'
  | 'react'
  | 'response'
  | 'media'
  | 'embedding'
  | 'background'
  | 'unknown';

const NODE_FAMILY_EXACT: Record<string, NodeFamily> = {
  compaction: 'analysis',
  router: 'analysis',
  // Router-phase LLM calls observed at runtime: the analyzer itself and the
  // pre-planner memory resolution (exact entries win over the `_extraction`
  // suffix rule, which would misfile the latter as a background family).
  query_analyzer: 'analysis',
  memory_reference_extraction: 'analysis',
  planner: 'planning',
  semantic_validator: 'planning',
  clarification: 'planning',
  hitl_dispatch: 'hitl',
  approval_gate: 'hitl',
  for_each_confirm: 'hitl',
  task_orchestrator: 'execution',
  parallel_executor: 'execution',
  response: 'response',
  fallback_response: 'response',
  // Route label used by the entry header ("chat" = conversation → response).
  chat: 'response',
  image_generation: 'media',
  tts: 'media',
  stt: 'media',
  voice: 'media',
};

/**
 * Resolve the family of a LangGraph node name.
 *
 * Exact names first, then structural rules (`react_*`, `embedding*`,
 * `*_extraction`, `*_agent`). Anything else is `unknown` — never a guess.
 */
export function nodeFamily(nodeName: string): NodeFamily {
  const name = nodeName.toLowerCase();
  const exact = NODE_FAMILY_EXACT[name];
  if (exact) return exact;
  if (name.startsWith('react_')) return 'react';
  if (name.startsWith('embedding')) return 'embedding';
  if (name.endsWith('_extraction')) return 'background';
  if (name.endsWith('_agent')) return 'execution';
  return 'unknown';
}

/**
 * Identity chip classes per family — every raw hue ships its `dark:`
 * counterpart (the old `NODE_COLORS` were dark-only and unreadable in the
 * light theme); `response` rides the theme token.
 */
const NODE_FAMILY_CHIP: Record<NodeFamily, string> = {
  analysis: 'bg-violet-500/15 text-violet-700 dark:text-violet-300 border-violet-500/30',
  planning: 'bg-blue-500/15 text-blue-700 dark:text-blue-300 border-blue-500/30',
  hitl: 'bg-amber-500/15 text-amber-700 dark:text-amber-300 border-amber-500/30',
  execution: 'bg-orange-500/15 text-orange-700 dark:text-orange-300 border-orange-500/30',
  react: 'bg-fuchsia-500/15 text-fuchsia-700 dark:text-fuchsia-300 border-fuchsia-500/30',
  response: 'bg-primary/15 text-primary border-primary/30',
  media: 'bg-pink-500/15 text-pink-700 dark:text-pink-300 border-pink-500/30',
  embedding: 'bg-teal-500/15 text-teal-700 dark:text-teal-300 border-teal-500/30',
  background: 'bg-slate-500/15 text-slate-700 dark:text-slate-300 border-slate-500/30',
  unknown: 'bg-muted text-muted-foreground border-border',
};

/** Bi-theme identity chip classes for a node name. */
export function nodeChipClasses(nodeName: string): string {
  return NODE_FAMILY_CHIP[nodeFamily(nodeName)];
}
