/**
 * Constants for Debug Panel
 *
 * Centralizes all magic numbers and hardcoded values for easier
 * maintenance and visual consistency.
 */

/**
 * Colors for confidence badges (dark mode compatible)
 */
export const CONFIDENCE_COLORS = {
  high: 'bg-green-500/20 text-green-400 border-green-500/30',
  medium: 'bg-yellow-500/20 text-yellow-400 border-yellow-500/30',
  low: 'bg-red-500/20 text-red-400 border-red-500/30',
} as const;

/**
 * Colors for score bars (darker versions for bars)
 */
export const CONFIDENCE_BAR_COLORS = {
  high: 'bg-green-500',
  medium: 'bg-yellow-500',
  low: 'bg-red-400',
} as const;

/**
 * Colors for token budget zones (dark mode compatible)
 */
export const ZONE_COLORS = {
  safe: 'bg-green-500/20 text-green-400 border-green-500/30',
  warning: 'bg-yellow-500/20 text-yellow-400 border-yellow-500/30',
  critical: 'bg-orange-500/20 text-orange-400 border-orange-500/30',
  emergency: 'bg-red-500/20 text-red-400 border-red-500/30',
} as const;

/**
 * Colors for token budget zones (progress bars)
 */
export const ZONE_BAR_COLORS = {
  safe: 'bg-green-500',
  warning: 'bg-yellow-500',
  critical: 'bg-orange-500',
  emergency: 'bg-red-500',
} as const;

/**
 * Colors for token budget zones (light backgrounds)
 */
export const ZONE_BACKGROUND_COLORS = {
  safe: 'bg-green-500/10',
  warning: 'bg-yellow-500/10',
  critical: 'bg-orange-500/10',
  emergency: 'bg-red-500/10',
} as const;

/**
 * Colors for planning strategies (dark mode compatible)
 */
export const STRATEGY_COLORS = {
  template_bypass: 'bg-blue-500/20 text-blue-400 border-blue-500/30',
  filtered_catalogue: 'bg-green-500/20 text-green-400 border-green-500/30',
  generative: 'bg-purple-500/20 text-purple-400 border-purple-500/30',
  panic_mode: 'bg-red-500/20 text-red-400 border-red-500/30',
} as const;

/**
 * Colors for LLM node names (dark mode compatible)
 * v3.1: Extended for all pipeline nodes
 */
export const NODE_COLORS = {
  router: 'bg-purple-500/20 text-purple-400 border-purple-500/30',
  planner: 'bg-blue-500/20 text-blue-400 border-blue-500/30',
  semantic_validator: 'bg-cyan-500/20 text-cyan-400 border-cyan-500/30',
  task_orchestrator: 'bg-indigo-500/20 text-indigo-400 border-indigo-500/30',
  parallel_executor: 'bg-orange-500/20 text-orange-400 border-orange-500/30',
  response: 'bg-primary/20 text-primary border-primary/30',
  default: 'bg-muted text-muted-foreground border-border',
} as const;

/**
 * Colors for statuses (pass/fail) (dark mode compatible)
 */
export const STATUS_COLORS = {
  passed: 'bg-green-500/20 text-green-400 border-green-500/30',
  failed: 'bg-red-500/20 text-red-400 border-red-500/30',
} as const;

/**
 * Colors for execution statuses (dark mode compatible)
 */
export const EXECUTION_STATUS_COLORS = {
  pending: 'bg-muted text-muted-foreground border-border',
  running: 'bg-blue-500/20 text-blue-400 border-blue-500/30',
  completed: 'bg-green-500/20 text-green-400 border-green-500/30',
  error: 'bg-red-500/20 text-red-400 border-red-500/30',
} as const;

/**
 * Maximum width of a score bar (in pixels)
 */
export const SCORE_BAR_MAX_WIDTH_PX = 100;

/**
 * Maximum number of scores to display in lists
 */
export const MAX_SCORES_DISPLAY = 15;

/**
 * Maximum length for truncating queries
 */
export const QUERY_TRUNCATE_LENGTH = 50;

/**
 * Maximum length for truncating model names
 */
export const MODEL_NAME_TRUNCATE_LENGTH = 100;

/**
 * Default threshold for determining if a domain passed
 * (used if thresholds are not provided by the backend)
 */
export const DEFAULT_DOMAIN_THRESHOLD = 0.15;

/**
 * Default threshold for determining if a tool passed
 */
export const DEFAULT_TOOL_THRESHOLD = 0.15;

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
 * Node order in the pipeline (for Request Lifecycle)
 * Aligned with DEBUG_PIPELINE_NODE_ORDER in apps/api/src/core/constants.py
 */
export const PIPELINE_NODE_ORDER = [
  'router',
  'planner',
  'semantic_validator',
  'task_orchestrator',
  'parallel_executor',
  'response',
] as const;

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
 * Refresh delay for health indicators (in ms)
 */
export const HEALTH_REFRESH_INTERVAL_MS = 5000;

/**
 * Progress bar height (in rem)
 */
export const PROGRESS_BAR_HEIGHT = '0.375rem'; // 1.5 (h-1.5)

/**
 * Token budget bar height (in rem)
 */
export const TOKEN_BAR_HEIGHT = '0.5rem'; // 2 (h-2)

/**
 * Reusable CSS classes for query backgrounds
 */
export const QUERY_BACKGROUND_CLASSES =
  'bg-muted/30 p-2 rounded text-foreground border border-border/50';

/**
 * Reusable CSS classes for error sections
 */
export const ERROR_SECTION_CLASSES =
  'mt-1 text-xs text-red-300 bg-red-900/20 p-2 rounded border border-red-700/50';

/**
 * Reusable CSS classes for warning sections
 */
export const WARNING_SECTION_CLASSES =
  'mt-1 text-xs text-yellow-300 bg-yellow-900/20 p-2 rounded border border-yellow-700/50';

/**
 * Reusable CSS classes for info sections
 */
export const INFO_SECTION_CLASSES =
  'mt-1 text-xs text-blue-300 bg-blue-900/20 p-2 rounded border border-blue-700/50';

/**
 * Reusable CSS classes for summary boxes
 */
export const SUMMARY_BOX_CLASSES = 'mb-3 p-2 bg-muted/30 rounded border border-border/50';

/**
 * Thresholds for determining cost type
 */
export const COST_THRESHOLDS = {
  low: 0.001, // < 0.1 cent
  medium: 0.01, // < 1 cent
  high: 0.1, // < 10 cents
} as const;

/**
 * Thresholds for determining duration type
 */
export const DURATION_THRESHOLDS = {
  fast: 100, // < 100ms
  normal: 1000, // < 1s
  slow: 5000, // < 5s
} as const;

/**
 * Badge sizes
 */
export const BADGE_SIZES = {
  xs: 'text-[9px] px-1.5 py-0',
  sm: 'text-[10px] px-2 py-0.5',
  md: 'text-xs px-2.5 py-1',
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
  /** Node badge (80px min) */
  nodeBadge: 'min-w-[80px]',
  /** Truncated value (200px max) */
  truncatedValue: 'max-w-[200px]',
  /** Wave label (3rem) */
  waveLabel: 'w-12',
  /** Wave counter (1.5rem) */
  waveCount: 'w-6',
  /** Numeric score (2.5rem) */
  scoreValue: 'w-10',
} as const;

/**
 * Available metric types
 */
export const METRIC_TYPES = [
  'intent_detection',
  'domain_selection',
  'routing_decision',
  'tool_selection',
  'token_budget',
  'planner_intelligence',
  'execution_timeline',
  'context_resolution',
  'query_info',
  'llm_calls',
] as const;

/**
 * Human-readable labels for metric types
 */
export const METRIC_TYPE_LABELS: Record<(typeof METRIC_TYPES)[number], string> = {
  intent_detection: 'Intent Detection',
  domain_selection: 'Domain Selection',
  routing_decision: 'Routing Decision',
  tool_selection: 'Tool Selection',
  token_budget: 'Token Budget',
  planner_intelligence: 'Planner Intelligence',
  execution_timeline: 'Execution Timeline',
  context_resolution: 'Context Resolution',
  query_info: 'Query Info',
  llm_calls: 'LLM Calls',
} as const;

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
 * Colors for fallback strategies (dark mode compatible)
 */
export const FALLBACK_STRATEGY_COLORS: Record<string, string> = {
  full_catalogue: 'bg-green-500/20 text-green-400 border-green-500/30',
  filtered_catalogue: 'bg-blue-500/20 text-blue-400 border-blue-500/30',
  reduced_descriptions: 'bg-yellow-500/20 text-yellow-400 border-yellow-500/30',
  primary_domain_only: 'bg-orange-500/20 text-orange-400 border-orange-500/30',
  simple_search: 'bg-red-500/20 text-red-400 border-red-500/30',
} as const;

/**
 * Helper to get a node color (with fallback)
 * Matches all pipeline nodes defined in PIPELINE_NODE_ORDER
 */
export function getNodeColor(nodeName: string): string {
  const lowerName = nodeName.toLowerCase();

  // Direct match first (exact node names from PIPELINE_NODE_ORDER)
  if (lowerName === 'router') return NODE_COLORS.router;
  if (lowerName === 'planner') return NODE_COLORS.planner;
  if (lowerName === 'semantic_validator') return NODE_COLORS.semantic_validator;
  if (lowerName === 'task_orchestrator') return NODE_COLORS.task_orchestrator;
  if (lowerName === 'parallel_executor') return NODE_COLORS.parallel_executor;
  if (lowerName === 'response') return NODE_COLORS.response;

  // Fuzzy fallback for variant naming (e.g., "planner_node" -> planner)
  if (lowerName.includes('router')) return NODE_COLORS.router;
  if (lowerName.includes('planner') || lowerName.includes('plan')) return NODE_COLORS.planner;
  if (lowerName.includes('semantic') || lowerName.includes('validator'))
    return NODE_COLORS.semantic_validator;
  if (lowerName.includes('orchestrator')) return NODE_COLORS.task_orchestrator;
  if (lowerName.includes('executor') || lowerName.includes('parallel'))
    return NODE_COLORS.parallel_executor;
  if (lowerName.includes('response') || lowerName.includes('resp')) return NODE_COLORS.response;

  return NODE_COLORS.default;
}

/**
 * Helper to get a confidence color
 */
export function getConfidenceColor(
  confidence: 'high' | 'medium' | 'low',
  type: 'badge' | 'bar' = 'badge'
): string {
  return type === 'badge' ? CONFIDENCE_COLORS[confidence] : CONFIDENCE_BAR_COLORS[confidence];
}

/**
 * Helper to get a zone color
 */
export function getZoneColor(
  zone: 'safe' | 'warning' | 'critical' | 'emergency',
  type: 'badge' | 'bar' | 'background' = 'badge'
): string {
  if (type === 'badge') return ZONE_COLORS[zone];
  if (type === 'bar') return ZONE_BAR_COLORS[zone];
  return ZONE_BACKGROUND_COLORS[zone];
}

/**
 * Helper to get a strategy color
 */
export function getStrategyColor(
  strategy: 'template_bypass' | 'filtered_catalogue' | 'generative' | 'panic_mode'
): string {
  return STRATEGY_COLORS[strategy];
}
