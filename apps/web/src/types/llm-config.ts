/**
 * LLM Configuration Admin types.
 * Mirrors backend Pydantic schemas for type safety.
 *
 * reasoning_effort is now a discriminated union (matches backend
 * src/core/reasoning_types.py + ModelCapabilities.reasoning_widget). The
 * shape is dispatched on the model's reasoning_widget — see ReasoningWidget
 * component for rendering and adapter.py for serialization rules.
 */

// --- Provider Keys ---

export interface ProviderKeyStatus {
  provider: string;
  display_name: string;
  has_db_key: boolean;
  masked_key: string | null;
  updated_at: string | null;
}

export interface ProviderKeysResponse {
  providers: ProviderKeyStatus[];
}

export interface ProviderKeyUpdate {
  key: string;
}

// --- Reasoning Effort ---

/** Widget type declared per model on llm_models.reasoning_widget. Drives
 * the rendering of the ReasoningWidget component. */
export type ReasoningWidgetType = 'none' | 'enum' | 'budget_int' | 'toggle_budget';

/** Numeric range for budget-based reasoning widgets. Mirrors backend
 * ReasoningBudgetRange in src/core/reasoning_types.py. */
export interface ReasoningBudgetRange {
  min: number;
  max: number;
  off_sentinel?: number | null;
  dynamic_sentinel?: number | null;
}

/** Discriminated union for reasoning_effort storage. Shape follows the
 * model's reasoning_widget. Mirrors backend ReasoningEffortValue. */
export type ReasoningEffortValue =
  | { effort: string }                              // widget=enum
  | { budget: number }                              // widget=budget_int
  | { enabled: boolean; budget?: number | null }    // widget=toggle_budget
  | null;

// --- LLM Agent Config ---

export interface LLMAgentConfig {
  provider: string;
  provider_config: string;
  model: string;
  temperature: number;
  top_p: number;
  frequency_penalty: number;
  presence_penalty: number;
  max_tokens: number;
  timeout_seconds: number | null;
  reasoning_effort: ReasoningEffortValue;
}

// --- LLM Type Config ---

/** Visual power tier for admin color-coding. */
export type PowerTier = 'critical' | 'high' | 'medium' | 'low';

/** Kind of model an LLM type expects. Drives the ?kinds= query param when
 * the frontend fetches /llm-config/metadata. */
export type LLMModelKind = 'chat' | 'image' | 'audio' | 'realtime' | 'tts' | 'embedding';

export interface LLMTypeInfo {
  llm_type: string;
  display_name: string;
  category: string;
  description_key: string;
  required_capabilities: string[];
  power_tier: PowerTier | null;
  required_kind: LLMModelKind;
}

export interface LLMTypeConfig {
  llm_type: string;
  info: LLMTypeInfo;
  effective: LLMAgentConfig;
  overrides: Record<string, unknown>;
  defaults: LLMAgentConfig;
  is_overridden: boolean;
}

export interface LLMTypeConfigUpdate {
  provider?: string | null;
  model?: string | null;
  temperature?: number | null;
  top_p?: number | null;
  frequency_penalty?: number | null;
  presence_penalty?: number | null;
  max_tokens?: number | null;
  timeout_seconds?: number | null;
  reasoning_effort?: ReasoningEffortValue;
  provider_config?: string | null;
}

export interface LLMConfigListResponse {
  configs: LLMTypeConfig[];
}

// --- Metadata ---

export interface ModelCapabilities {
  model_id: string;
  kind: LLMModelKind;
  max_output_tokens: number;
  supports_tools: boolean;
  supports_structured_output: boolean;
  supports_vision: boolean;
  is_reasoning_model: boolean;
  reasoning_widget: ReasoningWidgetType;
  reasoning_enum_values: string[] | null;
  reasoning_budget_range: ReasoningBudgetRange | null;
  reasoning_doc_i18n_key: string | null;
  // Per-model sampling support — drives conditional rendering of
  // temperature / top_p / frequency_penalty / presence_penalty inputs.
  // Mirrors llm_models.supports_* columns. Philosophy A: the UI shows
  // only what the API accepts.
  supports_temperature: boolean;
  supports_top_p: boolean;
  supports_frequency_penalty: boolean;
  supports_presence_penalty: boolean;
  cost_input: number | null;
  cost_output: number | null;
}

export interface ProviderModelsMetadata {
  providers: Record<string, ModelCapabilities[]>;
}

// --- Ollama dynamic discovery ---

export interface OllamaModelCapabilities extends ModelCapabilities {
  size: string | null;
  family: string | null;
}

export interface OllamaModelsResponse {
  models: OllamaModelCapabilities[];
  source: 'live' | 'fallback';
}

// --- UI helpers ---

export const LLM_CATEGORY_LABELS: Record<string, string> = {
  pipeline: 'Pipeline',
  domain_agents: 'Domain Agents',
  query_response: 'Query & Response',
  hitl: 'HITL',
  memory: 'Memory',
  background: 'Background',
  briefing: 'Briefing',
  specialized: 'Specialized',
};

export const LLM_CATEGORIES_ORDER = [
  'pipeline',
  'domain_agents',
  'query_response',
  'hitl',
  'memory',
  'background',
  'briefing',
  'specialized',
];
