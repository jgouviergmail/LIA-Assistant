/**
 * Constants for Debug Panel
 *
 * Non-colour constants only — every colour lives in `utils/tones.ts`, the
 * panel's single colour authority (semantic tokens + bi-theme node
 * identities). The 2026-08 overhaul deleted the legacy dark-only colour
 * tables and every constant with zero call sites.
 */

/**
 * Maximum number of scores to display in lists
 */
export const MAX_SCORES_DISPLAY = 15;

/**
 * Maximum length for truncating queries (history entry header)
 */
export const QUERY_TRUNCATE_LENGTH = 50;

/**
 * Maximum length for truncating model names
 */
export const MODEL_NAME_TRUNCATE_LENGTH = 100;

/**
 * Special value for cardinality_magnitude indicating "all items"
 * Aligned with CARDINALITY_ALL in apps/api/src/core/constants.py
 */
export const CARDINALITY_ALL_VALUE = 999;

/**
 * Labels for cardinality modes (FOR_EACH analysis)
 */
export const CARDINALITY_MODE_LABELS: Record<string, string> = {
  single: 'Single item',
  multiple: 'Multiple items',
  all: 'All items',
  each: 'Each item (iteration)',
} as const;

/**
 * Centralized default thresholds
 * (used if the backend does not provide thresholds)
 * Values aligned with apps/api/src/core/config/agents.py
 */
export const DEFAULT_THRESHOLDS = {
  intent: {
    high: 0.7,
    fallback: 0.5,
  },
  domain: {
    primary_min: 0.15,
    max_domains: 3,
  },
  routing: {
    min_confidence: 0.5,
    chat_semantic: 0.4,
    high_semantic: 0.7,
  },
  tool: {
    primary_min: 0.15,
    max_tools: 8,
  },
} as const;

/**
 * Sections open by default in the accordion
 * v3.1: All collapsed by default for more compact UI
 */
export const DEFAULT_OPEN_SECTIONS: string[] = [];

/**
 * Human-readable labels for fallback strategies (TokenBudget)
 * Maps to backend FallbackLevel enum
 */
export const FALLBACK_STRATEGY_LABELS: Record<string, string> = {
  full_catalogue: 'Full catalogue',
  filtered_catalogue: 'Filtered catalogue',
  reduced_descriptions: 'Reduced descriptions',
  primary_domain_only: 'Primary domain only',
  simple_search: 'Simple search',
} as const;

/**
 * Text sizes for the debug panel
 * Centralizes font size magic numbers
 */
export const DEBUG_TEXT_SIZES = {
  /** 9px - Very small (wave step IDs, compact badges) */
  tiny: 'text-[9px]',
  /** 10px - Small (labels, metadata, indicators) */
  small: 'text-[10px]',
  /** 11px - Mono (monospace values, scores, identifiers) */
  mono: 'text-[11px]',
} as const;

/**
 * Standardized widths for the debug panel
 * Centralizes width magic numbers
 */
export const DEBUG_WIDTHS = {
  /** Score bar (80px max) */
  scoreBar: 'max-w-[80px]',
  /** Truncated value (200px max) */
  truncatedValue: 'max-w-[200px]',
  /** Wave label (3rem) */
  waveLabel: 'w-12',
  /** Wave counter (1.5rem) */
  waveCount: 'w-6',
  /** Numeric score (2.5rem) */
  scoreValue: 'w-10',
} as const;
